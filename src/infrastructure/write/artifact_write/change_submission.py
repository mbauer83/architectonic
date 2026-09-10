"""Putting a set of recorded changes in front of a reviewer: replay, commit, push, mark.

Recording a change writes nothing upstream — that is the whole point of the two-tier model, and it
is why a change sits in the engagement repository as a semantic edit rather than a patch. Submitting
is where it stops being local: the recorded edits are re-applied to the enterprise repository, the
result is committed on the working branch and published, and only then are the changes marked.

**The replay is the write call, under the enterprise repository's own authority.** `admin_ops` is
the sanctioned way into that repository, so this calls it rather than reaching past it to a lower
writer that happens to take a root. Documents and diagrams there *are* the engagement computation
with the root assertion as a parameter; the entity edit is a separate implementation over the same
field vocabulary, which `test_both_authorities_edit_over_one_field_vocabulary` is what keeps true.
The rehearsal a rebase runs uses the engagement writers instead, because a temporary worktree infers
as an engagement — an asymmetry worth knowing about, and narrowed to that one arm by that test.

**Order of operations, and why it is not a transaction.** The replay is bracketed so a refusal
half-way leaves the enterprise checkout as it was. The commit is not: once it exists, the saga owns
what happens next, and `submission_saga` explains why a completed push cannot be rolled back by a
local reset. So the sequence is replay-or-restore, commit, then prepare-push-mark, where every step
after the commit converges on a retry rather than being undone.

**Nothing is marked until the remote confirms the branch.** `publish_submission` resolves the
outcome by reading the ref back, so a push that appeared to succeed against a branch someone else
moved raises rather than marking anybody's work submitted against content they did not produce.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.application.modeling.proposal_standing import PendingProposal, pending_proposals
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE, SUBMITTED_STATE
from src.application.modeling.submission_set import compose
from src.domain.clock import utc_now_iso
from src.domain.submission_phase import PushedSubmission
from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.git.enterprise_branch_lifecycle import ensure_working_branch
from src.infrastructure.git.git_repository_state import has_uncommitted_changes
from src.infrastructure.git.git_work_commits import commit_enterprise_work
from src.infrastructure.git.submission_saga import (
    prepare_submission,
    publish_submission,
    record_submitted,
)
from src.infrastructure.write.artifact_write.enterprise_replay import apply_to_enterprise
from src.infrastructure.write.artifact_write.promote_transaction import GitWorktreeTransaction
from src.infrastructure.write.artifact_write.proposal_lifecycle import (
    mark_proposal_state,
    restamp_base_revision,
)
from src.infrastructure.write.artifact_write.types import WriteResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.application.artifacts.query import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry

logger = logging.getLogger(__name__)


class SubmissionUnavailable(RuntimeError):
    """The submission cannot proceed. The message says what would have to change for it to."""


@dataclass(frozen=True, slots=True)
class SubmissionReport:
    """What the submission published, and what it marked."""

    branch: str
    commit: str
    submitted: tuple[str, ...]
    #: False on a converging retry, where the remote already carried the expected commit.
    pushed_now: bool


def submit_changes(
    proposal_ids: Sequence[str],
    *,
    repo: "ArtifactRepository",
    enterprise_root: Path | None,
    registry: "ArtifactRegistry",
    verifier: "ArtifactVerifier",
    clear_repo_caches: "Callable[[Path], None]",
) -> SubmissionReport:
    """Submit the changes `proposal_ids` names, in that order, for review upstream."""
    if enterprise_root is None:
        raise SubmissionUnavailable(
            "This deployment mounts no enterprise repository, so there is nowhere to submit a "
            "change to. The changes stay recorded here."
        )
    if has_uncommitted_changes(enterprise_root):
        raise SubmissionUnavailable(
            "The enterprise repository has unsaved changes. Submitting would publish them alongside "
            "the proposed ones; save or discard them first."
        )

    composed = compose(proposal_ids, pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)))
    ensure_working_branch(enterprise_root)
    _replay_onto_enterprise(
        composed, enterprise_root=enterprise_root, registry=registry, verifier=verifier,
        clear_repo_caches=clear_repo_caches,
    )
    commit = _commit_the_replay(composed, enterprise_root=enterprise_root)

    prepared = prepare_submission(enterprise_root, tuple(p.proposal_id for p in composed))
    outcome = publish_submission(enterprise_root, prepared)
    complete_submission(repo=repo, enterprise_root=enterprise_root)
    _record_published(enterprise_root, branch=outcome.branch, commit=outcome.commit)

    logger.info("Submitted %d change(s) on %s", len(composed), outcome.branch)
    return SubmissionReport(
        branch=outcome.branch,
        commit=commit,
        submitted=tuple(p.proposal_id for p in composed),
        pushed_now=outcome.pushed_now,
    )


def _replay_onto_enterprise(
    composed: tuple[PendingProposal, ...],
    *,
    enterprise_root: Path,
    registry: "ArtifactRegistry",
    verifier: "ArtifactVerifier",
    clear_repo_caches: "Callable[[Path], None]",
) -> None:
    """Re-apply each recorded edit in order, restoring the checkout if any of them is refused."""
    transaction = GitWorktreeTransaction(enterprise_root)
    transaction.begin()
    try:
        for proposal in composed:
            result = apply_to_enterprise(
                proposal.edit, enterprise_root=enterprise_root, registry=registry,
                verifier=verifier, clear_repo_caches=clear_repo_caches,
            )
            if not result.wrote:
                raise SubmissionUnavailable(
                    f"'{proposal.proposal_id}' no longer applies to "
                    f"'{proposal.edit.artifact_id}': {_refusal_of(result)}. Nothing has been "
                    "submitted. Rebasing the change is what brings it onto the artifact as it now "
                    "stands."
                )
    except BaseException:
        transaction.abort()
        raise
    transaction.commit()


def _commit_the_replay(
    composed: tuple[PendingProposal, ...],
    *,
    enterprise_root: Path,
) -> str:
    """Commit the replayed edits, verifying the whole tree the way any enterprise save does."""
    named = ", ".join(sorted({proposal.edit.artifact_id for proposal in composed}))
    try:
        return commit_enterprise_work(
            enterprise_root,
            f"Proposed change to {named}"
            if len(composed) == 1
            else f"Proposed changes to {named}",
        )
    except ValueError as nothing_to_commit:
        raise SubmissionUnavailable(
            "Replaying the changes altered nothing in the enterprise repository, so there is "
            "nothing to put in front of a reviewer. The artifacts already say what the changes "
            f"ask for ({nothing_to_commit})."
        ) from nothing_to_commit


def complete_submission(*, repo: "ArtifactRepository", enterprise_root: Path) -> tuple[str, ...]:
    """Mark the changes a published submission carries, and record the submission finished.

    The step between a branch reaching the remote and anyone here knowing it did. Both callers are
    the same situation seen at different moments: the submission that just pushed, and the one a
    previous process pushed before dying — `reconcile_submission` resolves the remote and leaves a
    `pushed` record precisely so this can finish it. That is D4c's transition, and it is one
    function rather than two so a change cannot be marked one way at submit time and another at
    startup.

    Returns what it marked. Nothing, and no complaint, where no submission is awaiting completion:
    at startup that is the ordinary case.
    """
    submission = enterprise_sync_state.load(enterprise_root).submission
    if not isinstance(submission, PushedSubmission):
        return ()
    marked = _mark_submitted(submission.intent.proposal_ids, repo=repo)
    record_submitted(enterprise_root, submission)
    return marked


def _mark_submitted(proposal_ids: tuple[str, ...], *, repo: "ArtifactRepository") -> tuple[str, ...]:
    """Mark each change submitted and restamp what the replay has just proven it against.

    The two facts belong together. The replay moved the enterprise artifact — by this change's own
    hand — so a base left at the older revision reads as staleness the moment the submission
    succeeds, and would send an author to rebase what they have just submitted.

    Read through `pending_proposals` rather than from the ids alone, because restamping needs the
    enterprise artifact each change is against, and that is stated in the recorded edit, which the
    one decoder of a change record is what reads.
    """
    by_id = {
        proposal.proposal_id: proposal
        for group in pending_proposals(
            repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)
        ).values()
        for proposal in group
    }
    marked: list[str] = []
    for proposal_id in proposal_ids:
        proposal = by_id.get(proposal_id)
        if proposal is None:
            # It was there when the set was composed. Losing it between then and here means the
            # branch is published carrying an edit nothing local claims — worth an operator's
            # attention, and not worth failing the other changes over.
            logger.warning("Change %s vanished between composition and marking", proposal_id)
            continue
        record = repo.get_entity(proposal_id)
        if record is not None and mark_proposal_state(
            record.path, artifact_id=proposal_id, state=SUBMITTED_STATE
        ):
            marked.append(proposal_id)
        restamp_base_revision(repo, proposal_id=proposal_id, target_id=proposal.target_id)
    return tuple(marked)


def _record_published(enterprise_root: Path, *, branch: str, commit: str) -> None:
    """Move the branch to `pending`, which is what stops a change reading `submitted` on an
    `accumulating` branch — the invariant the pair of lifecycles is there to keep."""
    state = enterprise_sync_state.load(enterprise_root)
    enterprise_sync_state.replace_lifecycle(
        enterprise_root,
        status="pending",
        branch=branch,
        branch_tip=commit,
        pushed_at=utc_now_iso(),
        commits_behind=state.commits_behind,
    )


def _refusal_of(result: WriteResult) -> str:
    """The verifier's own words, or the warning that stood in for them."""
    issues: list[Any] = (result.verification or {}).get("issues") or []
    if issues:
        return "; ".join(f"{issue['code']}: {issue['message']}" for issue in issues)
    return "; ".join(result.warnings) or "the write was refused without saying why"
