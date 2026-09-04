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

    branch_name = _new_working_branch_name(enterprise_root)
    rc, _, stderr = run_repo_git(enterprise_root, "checkout", "-b", branch_name)
    if rc != 0:
        raise RuntimeError(f"Failed to create enterprise working branch '{branch_name}': {stderr}")
    enterprise_sync_state.replace_lifecycle(enterprise_root, status="accumulating", branch=branch_name)
    logger.info("Created enterprise working branch: %s", branch_name)
    return branch_name




def _new_working_branch_name(enterprise_root: Path) -> str:
    """A working-branch name no ref in this repository already holds.

    The stamp is to the second, which is legible in a branch listing and was fine while a branch was
    only ever created from `synced` — minutes after the last one was abandoned. It is not fine for a
    replacement, which is opened *while* the branch it replaces still exists: created in the same
    second, the two names collide and `checkout -b` refuses with `a branch named … already exists`.
    That is the operation replacement exists for, failing exactly when it is used quickly.

    So the stamp is a starting point and the ref is the authority: suffix until nothing holds the
    name. Local refs only — the remote cannot hold a branch this repository never created, and a
    round trip per attempt would put the network in the path of naming something.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = f"arch/work-{stamp}"
    suffix = 2
    while local_ref_exists(enterprise_root, candidate):
        candidate = f"arch/work-{stamp}-{suffix}"
        suffix += 1
    return candidate


def _drop_remote_ref(enterprise_root: Path, branch: str) -> None:
    """Delete `origin/<branch>` if it is there, treating already-absent as success.

    The re-check after a failure is the point: a deletion that reports an error but whose ref is in
    fact gone has achieved the postcondition, and treating it as a failure would leave a caller
    retrying something already done. A failure with the ref still present is reported, so nothing
    upstream claims a removal that did not happen.
    """
    if not remote_ref_exists(enterprise_root, branch):
        return
    rc, _, stderr = run_repo_git(enterprise_root, "push", "origin", "--delete", branch, timeout=PUSH_TIMEOUT)
    if rc != 0 and remote_ref_exists(enterprise_root, branch):
        raise RuntimeError(f"Failed to delete remote branch '{branch}': {stderr}")


def _drop_local_ref(enterprise_root: Path, branch: str) -> None:
    """Delete the local branch if it is there, on the same already-absent-is-success rule.

    The caller must not be standing on it — abandon checks out `main` first, and a retirement is
    already on the replacement.
    """
    if not local_ref_exists(enterprise_root, branch):
        return
    rc, _, stderr = run_repo_git(enterprise_root, "branch", "-D", branch)
    if rc != 0 and local_ref_exists(enterprise_root, branch):
        raise RuntimeError(f"Failed to delete local branch '{branch}': {stderr}")


def open_replacement_branch(enterprise_root: Path, *, from_head: str) -> str:
    """Open a branch to replace one that is under review, keeping the reviewed one published.

    The existing primitives permit only *abandon then create*: `ensure_working_branch` returns the
    existing branch while the state is `accumulating` or `pending`, so creation is reachable only from
    `synced`, and `abandon_enterprise_branch` deletes the remote ref before anything else. Together
    that means the branch a reviewer is reading is deleted before its replacement exists — and if the
    creation then fails, the reviewed work is gone from the remote with nothing to point at.

    So: create first, record the old branch as superseded, and retire it separately once the
    replacement is confirmed. The superseded branch's remote ref is deliberately left alone here;
    `retire_superseded_branch` is what removes it, and until then a reviewer's link still resolves.

    Only from `pending`, because that is the only state where a branch is published and a reviewer
    could be looking at it. Replacing an `accumulating` branch is `ensure_working_branch`'s business,
    and there is nothing published to preserve.
    """
    state = enterprise_sync_state.load(enterprise_root)
    if not state.is_pending():
        raise ValueError(
            "A replacement branch is only opened for a submission under review; the enterprise "
            f"repository is {state.status}."
        )
    if state.superseded_branch is not None:
        raise ValueError(
            f"Branch '{state.superseded_branch}' is still awaiting retirement. Retire it before "
            "opening another replacement, or the first one is lost track of."
        )
    replaced = state.branch
    if not replaced:
        raise ValueError("The enterprise repository is pending review with no branch recorded")

    branch_name = _new_working_branch_name(enterprise_root)
    rc, _, stderr = run_repo_git(enterprise_root, "checkout", "-b", branch_name, from_head)
    if rc != 0:
        raise RuntimeError(f"Failed to open replacement branch '{branch_name}': {stderr}")

    enterprise_sync_state.replace_lifecycle(
        enterprise_root,
        status="accumulating",
        branch=branch_name,
        commits_behind=state.commits_behind,
    )
    enterprise_sync_state.replace_superseded_branch(enterprise_root, replaced)
    logger.info("Opened replacement branch %s; %s awaits retirement", branch_name, replaced)
    return branch_name


def retire_superseded_branch(enterprise_root: Path) -> str | None:
    """Remove the replaced branch, remote ref first, once its successor is established.

    Idempotent, and each postcondition treats *already absent* as success, so a retry after a partial
    failure converges — the same shape `abandon_enterprise_branch` uses, for the same reason: a
    half-retired branch must not need a person to finish it by hand.

    Returns the branch that was retired, or None when there was none to retire.
    """
    state = enterprise_sync_state.load(enterprise_root)
    branch = state.superseded_branch
    if branch is None:
        return None
    if branch == state.branch:
        raise ValueError(
            f"'{branch}' is recorded both as the current branch and as superseded; retiring it would "
            "delete the branch work is going to."
        )

    _drop_remote_ref(enterprise_root, branch)
    _drop_local_ref(enterprise_root, branch)

    enterprise_sync_state.replace_superseded_branch(enterprise_root, None)
    logger.info("Retired superseded branch %s", branch)
    return branch


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

    # 1. Remote ref absent. Decided by asking the *remote*, not by reading the local status: the
    #    push updates origin before the status is written, so a process that dies in between leaves
    #    the branch published while the aggregate still says `accumulating`. Gating this on
    #    `is_pending()` meant a discard in that window deleted the local branch, reported a
    #    withdrawal, and left the branch on origin for a reviewer to find — the "claimed withdrawal"
    #    the rest of this function exists to prevent, arrived through the status rather than the ref.
    #    A failed deletion whose ref is in fact gone counts as success; a failure with the ref still
    #    present preserves the state and reports.
    if branch:
        _drop_remote_ref(enterprise_root, branch)

    # 2. Checkout main (already on main = success).
    if current_branch(enterprise_root) != "main":
        rc, _, stderr = run_repo_git(enterprise_root, "checkout", "main")
        if rc != 0:
            raise RuntimeError(f"Failed to return enterprise repo to main: {stderr}")

    # 3. Local branch absent (already absent = success).
    if branch:
        _drop_local_ref(enterprise_root, branch)

    # 4. Aggregate cleared — only now that every postcondition holds.
    enterprise_sync_state.clear_lifecycle(enterprise_root)
    logger.info("Enterprise working branch abandoned: %s", branch)
    return branch


# ---------------------------------------------------------------------------
# Engagement repo
# ---------------------------------------------------------------------------


