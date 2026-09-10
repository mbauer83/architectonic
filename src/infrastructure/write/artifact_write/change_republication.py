"""Putting a rebased set back in front of a reviewer, on a branch of its own.

A change that has been submitted lives in two places at once: the record here, and a branch on the
enterprise remote that somebody may already be reading. Rebasing it moves the first. This is what
moves the second, and the whole question is *how*.

**Not a force-push.** The branch is the unit of review — a link, a diff, possibly comments — and
rewriting it changes the commits underneath a reviewer without saying so. So a rebase of a submitted
set opens a **new** branch on the current head, replays the set there, and publishes it; the branch
under review keeps its ref until the replacement is confirmed, and only then is it retired. The cost
is branch churn on the enterprise remote, which is visible, against silently invalidating a review in
progress, which is not.

**It pushes, rather than leaving the branch open.** Opening without publishing would leave the
changes reading `submitted` while their branch is `accumulating` — the one pairing of the two
lifecycles that the regional invariant forbids, and the state in which nothing local can tell you
whether a reviewer is looking at this work or at the version it replaced.

**Only for a set that is actually under review.** A draft has no published branch to protect, and its
rebase is finished when the record is restamped; opening a branch for one would publish work its
author never submitted.

**And the replacement has to carry everything the branch did.** It is opened on the current upstream
head and the set is replayed onto it, so anything else the old branch held is simply not there — and
the old branch is then retired, which deletes it from the remote. A promotion sharing the branch was
destroyed that way, present afterwards in neither branch. Two rules follow, and both are enforced
here: the set replayed is the **whole** submitted set the branch carries, in the order the
submission recorded, not just the one change an author happened to ask about; and if the branch
still differs from upstream in anything that set does not account for, the rebase is refused rather
than performed, because there is no mechanism here that could carry it across.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.modeling.proposal_standing import PendingProposal
from src.application.modeling.proposed_change import SUBMITTED_STATE
from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.git.enterprise_branch_lifecycle import (
    open_replacement_branch,
    retire_superseded_branch,
)
from src.infrastructure.git.git_repository_state import content_changed_against_upstream
from src.infrastructure.write.artifact_write.change_submission import (
    SubmissionReport,
    publish_on_the_current_branch,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.application.artifacts.query import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactVerifier
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry

logger = logging.getLogger(__name__)


class RepublicationUnsafe(RuntimeError):
    """Replacing the branch would leave something behind, so nothing was replaced."""


def needs_republishing(
    proposals: tuple[PendingProposal, ...],
    *,
    enterprise_root: Path,
) -> bool:
    """Whether this rebase has a published branch to replace.

    Both halves are required and neither implies the other. A change reads `submitted` only once a
    submission marked it, and the enterprise repository is `pending` only while a branch is on the
    remote — a reviewer who merged and deleted it leaves the first true and the second false, and
    opening a replacement for a branch nobody is reading is churn with no reader.
    """
    if not any(proposal.state == SUBMITTED_STATE for proposal in proposals):
        return False
    return enterprise_sync_state.load(enterprise_root).is_pending()


def the_whole_submitted_set(
    repo: "ArtifactRepository", enterprise_root: Path
) -> tuple[PendingProposal, ...]:
    """Every live submitted change, in the order the submission recorded for replaying them.

    The branch is the unit of review, so the replacement carries the set — not the one change an
    author clicked on. Replaying a subset onto a fresh branch would drop the rest of the set from
    the very branch that exists to carry it.

    The order is the submission's own: `SubmissionIntent` recorded it because replay order decides
    the result where two changes touch one artifact, and inferring it here would make a rebase
    produce different content from the submission it replaces. Anything submitted that the intent
    does not name follows, by id, so the set is still deterministic.
    """
    from src.application.modeling.proposal_standing import pending_proposals  # noqa: PLC0415
    from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE  # noqa: PLC0415

    live = {
        proposal.proposal_id: proposal
        for group in pending_proposals(
            repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)
        ).values()
        for proposal in group
        if proposal.state == SUBMITTED_STATE
    }
    submission = enterprise_sync_state.load(enterprise_root).submission
    recorded = submission.intent.proposal_ids if submission is not None else ()
    ordered = [live.pop(proposal_id) for proposal_id in recorded if proposal_id in live]
    return (*ordered, *(live[proposal_id] for proposal_id in sorted(live)))


def refuse_a_branch_carrying_more(
    replayed: tuple[PendingProposal, ...],
    *,
    repo: "ArtifactRepository",
    enterprise_root: Path,
    branch: str,
) -> None:
    """Refuse when the branch differs from upstream in anything the replay would not reproduce.

    The replacement is built from upstream plus this set, and the branch it replaces is deleted from
    the remote. Anything on it that the set does not account for — a promotion, most often, which is
    not a change and has its own review — would exist nowhere afterwards.

    Accounted for by *path*, resolved through the registry rather than by matching an id against a
    filename: the id-to-file question already has an owner, and a second reading of the naming
    convention is the defect this project keeps paying for.
    """
    changed = content_changed_against_upstream(enterprise_root, branch)
    if changed is None:
        raise RepublicationUnsafe(
            f"Could not compare '{branch}' against upstream, so replacing it might leave work "
            "behind. Nothing was changed."
        )
    accounted = {
        path.relative_to(enterprise_root).as_posix()
        for path in (repo.find_file_by_id(proposal.target_id) for proposal in replayed)
        if path is not None and path.is_relative_to(enterprise_root)
    }
    left_behind = sorted(set(changed) - accounted)
    if left_behind:
        raise RepublicationUnsafe(
            f"'{branch}' carries work these changes do not account for, and a replacement branch "
            f"would not carry it: {', '.join(left_behind)}. Get that reviewed or withdrawn first — "
            "rebasing would delete the branch holding it."
        )


def republish_on_a_replacement_branch(
    rebased: tuple[PendingProposal, ...],
    *,
    repo: "ArtifactRepository",
    enterprise_root: Path,
    registry: "ArtifactRegistry",
    verifier: "ArtifactVerifier",
    clear_repo_caches: "Callable[[Path], None]",
    from_head: str,
) -> SubmissionReport:
    """Open a branch on `from_head`, replay `rebased` onto it, publish it, and retire the old one.

    The retirement is last and separate. `open_replacement_branch` deliberately leaves the reviewed
    branch's remote ref alone, so a failure anywhere between here and the push leaves that branch
    exactly where the reviewer left it rather than deleting it in favour of something that never
    arrived.
    """
    replacement = open_replacement_branch(enterprise_root, from_head=from_head)
    report = publish_on_the_current_branch(
        rebased, repo=repo, enterprise_root=enterprise_root, registry=registry,
        verifier=verifier, clear_repo_caches=clear_repo_caches, verb="Rebased",
    )
    retired = retire_superseded_branch(enterprise_root)
    logger.info("Republished %d change(s) on %s; retired %s", len(rebased), replacement, retired)
    return report
