"""Publishing a set of proposed changes for review, in steps that survive a crash between them.

`push_enterprise_branch` stamps the aggregate `pending` immediately after the push returns. That is
truthful only while nothing goes wrong: the push updates a remote nothing local can roll back, and
the local write happens afterwards, so a crash in between leaves a published review branch that the
aggregate says nothing about. The next attempt then opens a second branch, or a withdrawal reports
success over a branch that is still there.

This module runs the same publication as a saga:

1. **Prepare.** Record the intent — which changes, which branch, which commit is expected on the
   remote — and persist it *before* touching the network.
2. **Push**, unless the remote already carries the expected commit, which is what a retry finds.
3. **Resolve** by reading the remote ref back and comparing it against the expected commit. Only
   then is the submission `pushed`.

Status is **derived from the ref**, never stamped from the fact that a push call returned. The two
differ exactly when it matters.

**A ref at an unexpected commit fails closed.** It is not a completed push to recognise: it means the
branch moved for a reason this process did not cause — a reviewer's amend, a force-push, another
workspace. Treating it as a successful idempotent retry would mark changes submitted against content
nobody here produced.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.domain.clock import utc_now_iso
from src.domain.submission_phase import (
    PreparedSubmission,
    PushedSubmission,
    SubmissionIntent,
)
from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.git._git_command import PUSH_TIMEOUT, run_repo_git
from src.infrastructure.git.enterprise_branch_lifecycle import submission_preflight
from src.infrastructure.git.git_repository_state import current_commit, remote_ref_commit

logger = logging.getLogger(__name__)


class SubmissionConflict(RuntimeError):
    """The remote branch is not where this submission left it, so it must not be overwritten."""


@dataclass(frozen=True, slots=True)
class SubmissionOutcome:
    """What the saga achieved, and whether the push itself still had to happen.

    `pushed_now` is False on a converging retry — the remote already carried the expected commit —
    which is what lets a caller distinguish "published" from "was already published" without
    re-reading the remote itself.
    """

    branch: str
    commit: str
    proposal_ids: tuple[str, ...]
    pushed_now: bool


def prepare_submission(enterprise_root: Path, proposal_ids: tuple[str, ...]) -> PreparedSubmission:
    """Record what the submission intends, before anything reaches the remote.

    The expected commit is the enterprise branch's current tip: what a reviewer will find if the push
    succeeds. Recording it is what makes the push idempotent — without it, a retry cannot tell its own
    completed push from a branch someone else moved.
    """
    branch = submission_preflight(enterprise_root)
    commit = current_commit(enterprise_root)
    if not commit:
        raise RuntimeError("Enterprise repository has no commit to submit")

    prepared = PreparedSubmission(
        intent=SubmissionIntent(proposal_ids=proposal_ids, branch=branch, expected_commit=commit)
    )
    _persist(enterprise_root, prepared)
    logger.info("Submission prepared: %d change(s) on %s at %.7s", len(proposal_ids), branch, commit)
    return prepared


def publish_submission(enterprise_root: Path, prepared: PreparedSubmission) -> SubmissionOutcome:
    """Push the prepared branch and resolve the outcome from the remote ref.

    Safe to call again after any failure. The push is skipped when the remote already carries the
    expected commit, and the resolution below is the same in both cases — a retry converges on one
    review branch and one truthful status rather than on a second branch.
    """
    intent = prepared.intent
    published = remote_ref_commit(enterprise_root, intent.branch)
    pushed_now = published != intent.expected_commit

    if pushed_now:
        _refuse_a_moved_branch(published, intent)
        rc, _, stderr = run_repo_git(
            enterprise_root, "push", "-u", "origin", intent.branch, timeout=PUSH_TIMEOUT
        )
        if rc != 0:
            raise RuntimeError(f"Failed to push enterprise branch '{intent.branch}': {stderr}")

    confirmed = remote_ref_commit(enterprise_root, intent.branch)
    if confirmed != intent.expected_commit:
        raise SubmissionConflict(
            f"Branch '{intent.branch}' on origin is at {confirmed or 'no commit'}, not the "
            f"{intent.expected_commit} this submission published. Nothing has been marked submitted."
        )

    pushed = prepared.pushed(at=utc_now_iso())
    _persist(enterprise_root, pushed)
    logger.info(
        "Submission published: %s at %.7s (%s)",
        intent.branch,
        intent.expected_commit,
        "pushed" if pushed_now else "already on origin",
    )
    return SubmissionOutcome(
        branch=intent.branch,
        commit=intent.expected_commit,
        proposal_ids=intent.proposal_ids,
        pushed_now=pushed_now,
    )


def _refuse_a_moved_branch(published: str | None, intent: SubmissionIntent) -> None:
    """A branch that exists at some *other* commit is not ours to overwrite.

    An absent ref is the ordinary first push. A ref at a different commit means the branch moved for
    a reason this process did not cause, and `push -u` would either be refused by the remote or
    force the other work away depending on configuration — neither is an outcome to discover after
    marking changes submitted.
    """
    if published is not None:
        raise SubmissionConflict(
            f"Branch '{intent.branch}' already exists on origin at {published}, but this submission "
            f"was prepared against {intent.expected_commit}. Someone else has moved it; nothing has "
            "been pushed."
        )


def _persist(enterprise_root: Path, phase: PreparedSubmission | PushedSubmission) -> None:
    """Write the phase onto the aggregate, leaving the rest of the lifecycle alone."""
    current = enterprise_sync_state.load(enterprise_root)
    enterprise_sync_state.replace_submission(enterprise_root, phase, status=current.status)
