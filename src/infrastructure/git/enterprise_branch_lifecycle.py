"""The enterprise review branch, from opening one to submitting or abandoning it.

One branch accumulates promoted work until it is submitted for review; the states it moves through —
`synced`, `accumulating`, `pending` — are what a status read reports and what a submission preflight
checks. This is the module the change-submission saga extends, which is why it was separated from the
questions it asks and the commits it makes rather than growing further in place.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.domain.clock import utc_now_iso
from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.git._git_command import PUSH_TIMEOUT, run_repo_git
from src.infrastructure.git.git_repository_state import (
    current_branch,
    current_commit,
    has_uncommitted_changes,
    local_ref_exists,
    remote_ref_exists,
)

logger = logging.getLogger(__name__)

def ensure_working_branch(enterprise_root: Path) -> str:
    """Ensure the enterprise checkout is on a working branch, creating one if SYNCED.

    Safe to call repeatedly — idempotent when already on the correct branch.
    Returns the working branch name.  Raises RuntimeError if branch creation fails.
    """
    state = enterprise_sync_state.load(enterprise_root)

    if state.status in ("accumulating", "pending"):
        branch = current_branch(enterprise_root)
        if branch:
            if branch != state.branch:
                logger.warning(
                    "Enterprise branch mismatch: state=%s actual=%s — reconciling",
                    state.branch,
                    branch,
                )
                enterprise_sync_state.replace_lifecycle(
                    enterprise_root,
                    status=state.status,
                    branch=branch,
                    branch_tip=state.branch_tip,
                    pushed_at=state.pushed_at,
                    commits_behind=state.commits_behind,
                )
            return branch

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"arch/work-{ts}"
    rc, _, stderr = run_repo_git(enterprise_root, "checkout", "-b", branch_name)
    if rc != 0:
        raise RuntimeError(f"Failed to create enterprise working branch '{branch_name}': {stderr}")
    enterprise_sync_state.replace_lifecycle(enterprise_root, status="accumulating", branch=branch_name)
    logger.info("Created enterprise working branch: %s", branch_name)
    return branch_name




def submission_preflight(enterprise_root: Path) -> str:
    """The branch :func:`push_enterprise_branch` would publish, without publishing it.

    Exists so a caller can preview a submission — the push reaches a *shared remote*, so
    "what would this do" has to be answerable without doing it. It raises the same errors, with the
    same messages, that the push itself would, which is the point: the checks live here and the push
    calls this, so a preview cannot claim a submission the live call would refuse. Restating the
    conditions at the preview's own call site would let the two drift, and it would drift silently —
    the preview would keep answering "ready" after a new precondition was added to the push.
    """
    branch = current_branch(enterprise_root)
    if not branch:
        raise RuntimeError("Enterprise repo is in detached HEAD state")
    if has_uncommitted_changes(enterprise_root):
        raise ValueError("Enterprise repository has unsaved changes. Save your work before submitting for review.")
    return branch


def push_enterprise_branch(enterprise_root: Path) -> str:
    """Push the working branch to origin and transition the state to PENDING.

    Content-neutral git operation: it publishes already-committed (and therefore
    already-verified) work and introduces no artifact content, so it is exempt
    from save verification. Returns the branch name. Raises ValueError if there
    are unsaved changes, RuntimeError if the push fails.
    """
    state = enterprise_sync_state.load(enterprise_root)
    branch = submission_preflight(enterprise_root)
    rc, _, stderr = run_repo_git(enterprise_root, "push", "-u", "origin", branch, timeout=PUSH_TIMEOUT)
    if rc != 0:
        raise RuntimeError(f"Failed to push enterprise branch '{branch}': {stderr}")
    commit = current_commit(enterprise_root) or ""
    enterprise_sync_state.replace_lifecycle(
        enterprise_root,
        status="pending",
        branch=branch,
        branch_tip=commit,
        pushed_at=utc_now_iso(),
        commits_behind=state.commits_behind,
    )
    logger.info("Enterprise branch submitted for review: %s", branch)
    return branch




def abandon_enterprise_branch(enterprise_root: Path) -> str | None:
    """Discard the working branch: an idempotent desired-state transition.

    Content-neutral git operation (branch cleanup, no artifact content) — exempt
    from save verification. Rejects when there is nothing to discard or the tree
    is dirty (never a silent success). Four postconditions, in order: remote ref
    absent → checkout ``main`` → local branch absent → aggregate cleared. Every
    step treats "already absent / already on main" as success, so a retry after
    any partial failure converges without recreating or requiring the remote
    ref; the aggregate stays pending until every postcondition holds.
    """
    state = enterprise_sync_state.load(enterprise_root)
    if state.is_synced():
        raise ValueError("Nothing to discard: the enterprise repository has no working branch.")
    if has_uncommitted_changes(enterprise_root):
        raise ValueError(
            "The enterprise working tree has unsaved changes. Save them first — Discard only removes the branch."
        )
    branch = state.branch

    # 1. Remote ref absent (pending submissions only). A failed deletion whose ref
    #    is in fact gone counts as success; a failure with the ref still present
    #    preserves the pending state and reports — no claimed withdrawal.
    if state.is_pending() and branch and remote_ref_exists(enterprise_root, branch):
        rc, _, stderr = run_repo_git(enterprise_root, "push", "origin", "--delete", branch, timeout=PUSH_TIMEOUT)
        if rc != 0 and remote_ref_exists(enterprise_root, branch):
            raise RuntimeError(f"Failed to delete remote branch '{branch}': {stderr}")

    # 2. Checkout main (already on main = success).
    if current_branch(enterprise_root) != "main":
        rc, _, stderr = run_repo_git(enterprise_root, "checkout", "main")
        if rc != 0:
            raise RuntimeError(f"Failed to return enterprise repo to main: {stderr}")

    # 3. Local branch absent (already absent = success).
    if branch and local_ref_exists(enterprise_root, branch):
        rc, _, stderr = run_repo_git(enterprise_root, "branch", "-D", branch)
        if rc != 0 and local_ref_exists(enterprise_root, branch):
            raise RuntimeError(f"Failed to delete local branch '{branch}': {stderr}")

    # 4. Aggregate cleared — only now that every postcondition holds.
    enterprise_sync_state.clear_lifecycle(enterprise_root)
    logger.info("Enterprise working branch abandoned: %s", branch)
    return branch


# ---------------------------------------------------------------------------
# Engagement repo
# ---------------------------------------------------------------------------


