"""Synchronous git operations for the enterprise repository branch lifecycle.

These functions run inside the write-queue executor thread (not the asyncio
event loop), so they use subprocess.run. Network operations (push/pull) inherit
the shared SSH environment from git_env.py, which is populated by GitSyncManager
on startup, so the same askpass credentials apply here as in the background sync.

Engagement-repo helpers are also here to keep all git commit/push logic in one place.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from src.config.git_identity import GitIdentity, load_service_git_identity, optional_git_author
from src.config.repo_paths import DIAGRAM_CATALOG, DOCS, MODEL
from src.domain.clock import utc_now_iso
from src.infrastructure.git import enterprise_sync_state
from src.infrastructure.mutation_adapters import run_git

logger = logging.getLogger(__name__)
_GIT_TIMEOUT = 30
_PUSH_TIMEOUT = 60

# Stage everything EXCEPT `.arch/` — the runtime sync-state directory. A blind
# `git add .` once carried .arch/enterprise-sync.json through a PR into
# origin/main; the pathspec exclude holds even when the repo has no .gitignore.
_STAGE_ALL_BUT_RUNTIME_STATE = ("add", "-A", "--", ".", ":(exclude).arch")


def _run(
    repo: Path,
    *args: str,
    timeout: float = _GIT_TIMEOUT,
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    from src.infrastructure.git.git_env import get_ssh_env

    env = dict(get_ssh_env() or os.environ)
    if env_overrides:
        env.update(env_overrides)
    result = run_git(
        repo,
        args,
        timeout=timeout,
        env=env,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------


def current_branch(repo: Path) -> str | None:
    rc, out, _ = _run(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return out if rc == 0 and out not in ("", "HEAD") else None


def current_commit(repo: Path) -> str | None:
    rc, out, _ = _run(repo, "rev-parse", "HEAD")
    return out if rc == 0 else None


def has_uncommitted_changes(repo: Path, *pathspecs: str) -> bool:
    # `.arch/` holds runtime sync state, never user work — it must not count as
    # (or ever be committed with) unsaved changes.
    args = ["status", "--porcelain", "--", *(pathspecs or (".",)), ":(exclude).arch"]
    rc, out, _ = _run(repo, *args)
    return rc == 0 and bool(out)


def commits_ahead_of_main(repo: Path) -> int:
    rc, out, _ = _run(repo, "rev-list", "--count", "origin/main..HEAD")
    try:
        return int(out) if rc == 0 else 0
    except ValueError:
        return 0


def commits_behind_main(repo: Path) -> int:
    rc, out, _ = _run(repo, "rev-list", "--count", "HEAD..origin/main")
    try:
        return int(out) if rc == 0 else 0
    except ValueError:
        return 0


def promotion_merged_into_main(repo: Path) -> bool:
    """Detect merge via content diff: empty diff means working branch is in origin/main."""
    rc, out, _ = _run(
        repo,
        "diff",
        "origin/main",
        "HEAD",
        "--",
        MODEL,
        DOCS,
        DIAGRAM_CATALOG,
    )
    return rc == 0 and not out


# ---------------------------------------------------------------------------
# Enterprise branch lifecycle
# ---------------------------------------------------------------------------


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
    rc, _, stderr = _run(enterprise_root, "checkout", "-b", branch_name)
    if rc != 0:
        raise RuntimeError(f"Failed to create enterprise working branch '{branch_name}': {stderr}")
    enterprise_sync_state.replace_lifecycle(enterprise_root, status="accumulating", branch=branch_name)
    logger.info("Created enterprise working branch: %s", branch_name)
    return branch_name


def commit_enterprise_work(
    enterprise_root: Path,
    message: str,
    *,
    author_name: str | None = None,
    author_email: str | None = None,
) -> str:
    """Stage and commit all changes in the enterprise repo. Returns the new commit hash.

    Verifies the whole working tree first (it may hold manually edited files);
    a failing tree rejects the save with no commit and no state change.
    """
    from src.infrastructure.write.save_commit_verification import assert_repository_verifies  # noqa: PLC0415

    author = optional_git_author(author_name, author_email)
    if not has_uncommitted_changes(enterprise_root):
        raise ValueError("No changes to save in the enterprise repository")
    assert_repository_verifies(enterprise_root)
    rc, _, stderr = _run(enterprise_root, *_STAGE_ALL_BUT_RUNTIME_STATE)
    if rc != 0:
        raise RuntimeError(f"Failed to stage enterprise changes: {stderr}")
    rc, _, stderr = _commit(
        enterprise_root,
        message,
        author=author,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to commit enterprise changes: {stderr}")
    commit = current_commit(enterprise_root) or ""
    logger.info("Enterprise work saved: %.7s — %s", commit, message)
    return commit


def checkpoint_worktree(repo: Path) -> tuple[str, str]:
    """Checkpoint the worktree for a promotion transaction: ``(head, checkpoint)``.

    A dirty tree (accumulated, not-yet-saved prior work) is committed with the
    service identity so a later ``reset --hard`` to the checkpoint cannot destroy
    it; a clean tree checkpoints as HEAD itself. ``.arch/`` runtime state is never
    staged (same pathspec rule as every other enterprise commit).
    """
    head = current_commit(repo)
    if head is None:
        raise RuntimeError("Cannot checkpoint enterprise worktree: no HEAD commit")
    if not has_uncommitted_changes(repo):
        return head, head
    rc, _, stderr = _run(repo, *_STAGE_ALL_BUT_RUNTIME_STATE)
    if rc != 0:
        raise RuntimeError(f"Failed to stage enterprise worktree for checkpoint: {stderr}")
    rc, _, stderr = _commit(repo, "promotion checkpoint (transient)", author=None)
    if rc != 0:
        raise RuntimeError(f"Failed to create promotion checkpoint commit: {stderr}")
    checkpoint = current_commit(repo)
    if checkpoint is None:
        raise RuntimeError("Promotion checkpoint commit did not produce a HEAD")
    return head, checkpoint


def restore_worktree_checkpoint(repo: Path, *, head: str, checkpoint: str) -> None:
    """Abort path: return the worktree to its exact pre-checkpoint state.

    ``reset --hard`` to the checkpoint restores every tracked file; ``clean``
    removes everything the promotion left untracked (``.arch/`` excepted — it is
    runtime state and was never part of the checkpoint); the final ``reset`` moves
    HEAD back so prior work is uncommitted again, exactly as before ``begin``.
    """
    rc, _, stderr = _run(repo, "reset", "--hard", checkpoint)
    if rc != 0:
        raise RuntimeError(f"Failed to reset enterprise worktree to promotion checkpoint: {stderr}")
    rc, _, stderr = _run(repo, "clean", "-fd", "--", ".", ":(exclude).arch")
    if rc != 0:
        raise RuntimeError(f"Failed to clean enterprise worktree after promotion abort: {stderr}")
    if checkpoint != head:
        rc, _, stderr = _run(repo, "reset", "--mixed", head)
        if rc != 0:
            raise RuntimeError(f"Failed to restore enterprise HEAD after promotion abort: {stderr}")


def release_worktree_checkpoint(repo: Path, *, head: str, checkpoint: str) -> None:
    """Success path: un-commit the transient checkpoint, keeping the tree as is,
    so prior work AND the promotion's writes are unsaved changes again — the
    accumulate-then-save lifecycle owns the actual commit."""
    if checkpoint == head:
        return
    rc, _, stderr = _run(repo, "reset", "--mixed", head)
    if rc != 0:
        raise RuntimeError(f"Failed to release promotion checkpoint: {stderr}")


def push_enterprise_branch(enterprise_root: Path) -> str:
    """Push the working branch to origin and transition the state to PENDING.

    Content-neutral git operation: it publishes already-committed (and therefore
    already-verified) work and introduces no artifact content, so it is exempt
    from save verification. Returns the branch name. Raises ValueError if there
    are unsaved changes, RuntimeError if the push fails.
    """
    state = enterprise_sync_state.load(enterprise_root)
    branch = current_branch(enterprise_root)
    if not branch:
        raise RuntimeError("Enterprise repo is in detached HEAD state")
    if has_uncommitted_changes(enterprise_root):
        raise ValueError("Enterprise repository has unsaved changes. Save your work before submitting for review.")
    rc, _, stderr = _run(enterprise_root, "push", "-u", "origin", branch, timeout=_PUSH_TIMEOUT)
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


def _remote_ref_exists(enterprise_root: Path, branch: str) -> bool:
    rc, out, _ = _run(enterprise_root, "ls-remote", "--heads", "origin", branch, timeout=_PUSH_TIMEOUT)
    if rc != 0:
        raise RuntimeError(f"Could not inspect origin for branch '{branch}'")
    return bool(out)


def _local_ref_exists(enterprise_root: Path, branch: str) -> bool:
    rc, _, _ = _run(enterprise_root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    return rc == 0


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
    if state.is_pending() and branch and _remote_ref_exists(enterprise_root, branch):
        rc, _, stderr = _run(enterprise_root, "push", "origin", "--delete", branch, timeout=_PUSH_TIMEOUT)
        if rc != 0 and _remote_ref_exists(enterprise_root, branch):
            raise RuntimeError(f"Failed to delete remote branch '{branch}': {stderr}")

    # 2. Checkout main (already on main = success).
    if current_branch(enterprise_root) != "main":
        rc, _, stderr = _run(enterprise_root, "checkout", "main")
        if rc != 0:
            raise RuntimeError(f"Failed to return enterprise repo to main: {stderr}")

    # 3. Local branch absent (already absent = success).
    if branch and _local_ref_exists(enterprise_root, branch):
        rc, _, stderr = _run(enterprise_root, "branch", "-D", branch)
        if rc != 0 and _local_ref_exists(enterprise_root, branch):
            raise RuntimeError(f"Failed to delete local branch '{branch}': {stderr}")

    # 4. Aggregate cleared — only now that every postcondition holds.
    enterprise_sync_state.clear_lifecycle(enterprise_root)
    logger.info("Enterprise working branch abandoned: %s", branch)
    return branch


# ---------------------------------------------------------------------------
# Engagement repo
# ---------------------------------------------------------------------------


def commit_engagement_work(
    engagement_root: Path,
    message: str,
    *,
    author_name: str | None = None,
    author_email: str | None = None,
) -> str:
    """Stage and commit all changes in the engagement repo. Returns the commit hash.

    Verifies the whole working tree first (it may hold manually edited files);
    a failing tree rejects the save with no commit and no state change.
    """
    from src.infrastructure.write.save_commit_verification import assert_repository_verifies  # noqa: PLC0415

    author = optional_git_author(author_name, author_email)
    if not has_uncommitted_changes(engagement_root):
        raise ValueError("No changes to save in the engagement repository")
    assert_repository_verifies(engagement_root)
    rc, _, stderr = _run(engagement_root, *_STAGE_ALL_BUT_RUNTIME_STATE)
    if rc != 0:
        raise RuntimeError(f"Failed to stage engagement changes: {stderr}")
    rc, _, stderr = _commit(
        engagement_root,
        message,
        author=author,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to commit engagement changes: {stderr}")
    commit = current_commit(engagement_root) or ""
    logger.info("Engagement work saved: %.7s — %s", commit, message)
    return commit


def push_engagement(engagement_root: Path) -> None:
    """Push the engagement repo's current branch to origin."""
    rc, _, stderr = _run(engagement_root, "push", timeout=_PUSH_TIMEOUT)
    if rc != 0:
        raise RuntimeError(f"Failed to push engagement changes: {stderr}")
    logger.info("Engagement changes pushed to remote")


def _commit(repo: Path, message: str, *, author: GitIdentity | None) -> tuple[int, str, str]:
    service = load_service_git_identity()
    env = {
        "GIT_COMMITTER_NAME": service.name,
        "GIT_COMMITTER_EMAIL": service.email,
    }
    if author is not None:
        env.update(
            {
                "GIT_AUTHOR_NAME": author.name,
                "GIT_AUTHOR_EMAIL": author.email,
            }
        )
    return _run(
        repo,
        "-c",
        f"user.name={service.name}",
        "-c",
        f"user.email={service.email}",
        "commit",
        "-m",
        message,
        env_overrides=env,
    )
