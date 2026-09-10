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
