"""Taking, restoring and releasing a checkpoint of a repository's working tree.

A transaction primitive rather than a branch operation: `GitWorktreeTransaction` uses these to put
the enterprise checkout back the way it found it when a promotion fails partway. Kept apart from the
branch lifecycle because restoring a working tree is not part of any branch's story, and because the
write path imports these three and nothing else from this package.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.infrastructure.git._git_command import (
    STAGE_ALL_BUT_RUNTIME_STATE,
    commit_with_identity,
    run_repo_git,
)
from src.infrastructure.git.git_repository_state import current_commit, has_uncommitted_changes

logger = logging.getLogger(__name__)

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
    rc, _, stderr = run_repo_git(repo, *STAGE_ALL_BUT_RUNTIME_STATE)
    if rc != 0:
        raise RuntimeError(f"Failed to stage enterprise worktree for checkpoint: {stderr}")
    rc, _, stderr = commit_with_identity(repo, "promotion checkpoint (transient)", author=None)
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
    rc, _, stderr = run_repo_git(repo, "reset", "--hard", checkpoint)
    if rc != 0:
        raise RuntimeError(f"Failed to reset enterprise worktree to promotion checkpoint: {stderr}")
    rc, _, stderr = run_repo_git(repo, "clean", "-fd", "--", ".", ":(exclude).arch")
    if rc != 0:
        raise RuntimeError(f"Failed to clean enterprise worktree after promotion abort: {stderr}")
    if checkpoint != head:
        rc, _, stderr = run_repo_git(repo, "reset", "--mixed", head)
        if rc != 0:
            raise RuntimeError(f"Failed to restore enterprise HEAD after promotion abort: {stderr}")


def release_worktree_checkpoint(repo: Path, *, head: str, checkpoint: str) -> None:
    """Success path: un-commit the transient checkpoint, keeping the tree as is,
    so prior work AND the promotion's writes are unsaved changes again — the
    accumulate-then-save lifecycle owns the actual commit."""
    if checkpoint == head:
        return
    rc, _, stderr = run_repo_git(repo, "reset", "--mixed", head)
    if rc != 0:
        raise RuntimeError(f"Failed to release promotion checkpoint: {stderr}")


