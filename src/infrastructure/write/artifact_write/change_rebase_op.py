"""Bringing a recorded change onto the enterprise artifact as it stands now.

Staleness is the steady state of anything that waits: the enterprise branch moves while changes sit
unreviewed. A product that can only *report* staleness leaves an author with no move except to redo
the work, which is why this is an operation rather than a status.

**Three outcomes, all nameable** (`change_rebase` decides which):

* **clean** — the recorded edit still applies and still verifies, so the change is restamped against
  what it was just proven against. Its fields do not change: they are the author's intent, and the
  intent is what re-applied.
* **superseded** — the artifact already says what the change asked. Reported, never acted on: closing
  it here would be this operation deciding that a coincidence is an integration, which is the
  judgement `integration_sweep` deliberately reserves for changes that were actually submitted.
* **conflicting** — the verifier's own refusal, carried verbatim. Nothing is written.

The rehearsal happens in a throwaway worktree, so a set full of conflicts leaves the enterprise
checkout exactly as it was — and so that a replay is a real write, judged by the real verifier,
rather than a simulation of one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.modeling.change_rebase import RehearsedRebase
from src.application.modeling.proposal_standing import PendingProposal
from src.infrastructure.git.git_repository_state import UPSTREAM_REF
from src.infrastructure.write.artifact_write.change_republication import (
    RepublicationUnsafe,
    needs_republishing,
    refuse_a_branch_carrying_more,
    republish_on_a_replacement_branch,
    the_whole_submitted_set,
)
from src.infrastructure.write.artifact_write.change_submission import SubmissionReport
from src.infrastructure.write.artifact_write.rebase_rehearsal import rehearse_against, rehearsing
from src.infrastructure.write.artifact_write.rebase_replay import rehearser_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.application.artifacts.query import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry

logger = logging.getLogger(__name__)


class RebaseUnavailable(RuntimeError):
    """A rebase was asked for where it cannot be attempted, with the reason an operator can act on."""


@dataclass(frozen=True, slots=True)
class RebaseReport:
    """What the rehearsal concluded, which changes were restamped, and where they were republished."""

    rehearsed: RehearsedRebase
    restamped: tuple[str, ...]
    #: The replacement branch a submitted set was republished on, or None where there was no
    #: published branch to replace — every draft rebase, and a submitted one whose reviewer has
    #: already merged and deleted the branch.
    republished: "SubmissionReport | None" = None

    def summary(self) -> str:
        published = f"; republished on {self.republished.branch}" if self.republished else ""
        return f"{self.rehearsed.summary()}; {len(self.restamped)} restamped{published}"


def rebase_changes(
    proposals: tuple[PendingProposal, ...],
    *,
    enterprise_root: Path | None,
    repo: "ArtifactRepository",
    registry: "ArtifactRegistry",
    verifier: "ArtifactVerifier",
    clear_repo_caches: "Callable[[Path], None]",
) -> RebaseReport:
    """Rehearse `proposals` against the head they must apply to, restamping the ones that still do.

    **Which head that is depends on where the set already is.** A draft has been applied nowhere, so
    what it is against is the enterprise artifact as this repository holds it, and `HEAD` is that. A
    submitted set has already been replayed onto the working branch — rehearsing *there* would find
    every change made and call the whole set superseded, which is the answer that ended the first
    version of this. What it must apply to is the upstream its review branch will be merged into.

    `enterprise_root` is None on a deployment that mounts no enterprise repository, where a rebase
    cannot be attempted at all — there is nothing to re-apply against. Refused rather than reported
    as a conflict, which would blame the change for the deployment's shape.
    """
    if enterprise_root is None:
        raise RebaseUnavailable(
            "This repository does not hold the enterprise content these changes are against, so "
            "there is nothing to bring them onto. A rebase runs where both repositories are mounted."
        )
    if not proposals:
        return RebaseReport(rehearsed=RehearsedRebase(()), restamped=())

    republishing = needs_republishing(proposals, enterprise_root=enterprise_root)
    if republishing:
        # The branch is the unit of review, so the set is the branch's, not the one change an
        # author asked about — a replacement carrying a subset would drop the rest of the set from
        # the very branch that exists to carry it.
        proposals = the_whole_submitted_set(repo, enterprise_root) or proposals
    start_point = UPSTREAM_REF if republishing else "HEAD"
    with rehearsing(enterprise_root, start_point=start_point) as worktree, rehearser_for(worktree) as rehearser:
        rehearsed = rehearse_against(
            worktree,
            [(proposal.proposal_id, proposal.edit) for proposal in proposals],
            read_current=rehearser.read_current,
            apply_edit=rehearser.apply_edit,
        )

    report = RebaseReport(rehearsed=rehearsed, restamped=_restamp_clean(rehearsed, proposals, repo))
    # What the rehearsal *proved*, not what the restamp happened to write. A change already carrying
    # the revision it was just proven against is restamped to the same value and reports no change —
    # which is not a reason to withhold it from the branch a reviewer reads.
    proven = frozenset(classified.proposal_id for classified in rehearsed.with_outcome("clean"))
    if not proven or not republishing:
        return report
    # A superseded or conflicting change is not put in front of anyone, and a set of nothing but
    # those has nothing to republish.
    replayed = tuple(p for p in proposals if p.proposal_id in proven)
    try:
        refuse_a_branch_carrying_more(
            replayed, repo=repo, enterprise_root=enterprise_root, branch=_published_branch(enterprise_root)
        )
        republished = republish_on_a_replacement_branch(
            replayed, repo=repo, enterprise_root=enterprise_root, registry=registry,
            verifier=verifier, clear_repo_caches=clear_repo_caches, from_head=start_point,
        )
    except RepublicationUnsafe as unsafe:
        # The rehearsal stands and the restamps stand; what is refused is replacing the branch.
        raise RebaseUnavailable(str(unsafe)) from unsafe
    return replace(report, republished=republished)


def _published_branch(enterprise_root: Path) -> str:
    """The branch under review. `needs_republishing` has already established there is one."""
    from src.infrastructure.git import enterprise_sync_state  # noqa: PLC0415

    return enterprise_sync_state.load(enterprise_root).branch or ""


def _restamp_clean(
    rehearsed: RehearsedRebase,
    proposals: tuple[PendingProposal, ...],
    repo: "ArtifactRepository",
) -> tuple[str, ...]:
    """Record the revision each clean change has now been proven against."""
    from src.infrastructure.write.artifact_write.proposal_lifecycle import (  # noqa: PLC0415
        restamp_base_revision,
    )

    known = {proposal.proposal_id for proposal in proposals}
    return tuple(
        classified.proposal_id
        for classified in rehearsed.with_outcome("clean")
        if classified.proposal_id in known
        and restamp_base_revision(
            repo, proposal_id=classified.proposal_id, target_id=classified.target_id
        )
    )
