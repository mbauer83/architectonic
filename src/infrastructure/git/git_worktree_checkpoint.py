"""Taking, restoring and releasing a checkpoint of a repository's working tree.

A transaction primitive rather than a branch operation: `GitWorktreeTransaction` uses these to put
the enterprise checkout back the way it found it when a promotion fails partway. Kept apart from the
branch lifecycle because restoring a working tree is not part of any branch's story, and because the
write path imports these three and nothing else from this package.

**A checkpoint records the branch, not only two commits.** It used to record `(head, checkpoint)`, and
restoring them put the *commits* back while leaving HEAD wherever the failed operation had moved it.
Measured against a conflicted rebase: the checkout came back **detached**, `.git/rebase-merge`
survived, every later rebase failed with "there is already a rebase-merge directory", and the restore
reported success throughout. `submission_preflight` refuses a detached HEAD, so one failed operation
took down every submission, save and discard until a person intervened by hand.

Two things follow, and both are in `restore_worktree_checkpoint`: an operation git is still in the
middle of is **aborted through git's own abort**, which is what knows how to put a branch back; and
the branch is reattached explicitly, because a reset moves commits and never HEAD's attachment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.infrastructure.git._git_command import (
    STAGE_ALL_BUT_RUNTIME_STATE,
    commit_with_identity,
    run_repo_git,
)
from src.infrastructure.git.git_repository_state import (
    current_branch,
    current_commit,
    has_uncommitted_changes,
)

logger = logging.getLogger(__name__)

#: Where git records an operation it is part-way through, and the abort that unwinds each. Ordered
#: so the most specific state is recognised first: a cherry-pick and a revert both leave a
#: `sequencer` directory, and their own head files are what tell them apart.
_IN_PROGRESS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rebase-merge", ("rebase", "--abort")),
    ("rebase-apply", ("rebase", "--abort")),
    ("CHERRY_PICK_HEAD", ("cherry-pick", "--abort")),
    ("REVERT_HEAD", ("revert", "--abort")),
    ("MERGE_HEAD", ("merge", "--abort")),
)


@dataclass(frozen=True, slots=True)
class WorktreeCheckpoint:
    """What a working tree was, in enough detail to put it back.

    `branch` is None only where the checkout was *already* detached when the checkpoint was taken —
    a state to restore faithfully rather than to repair. Recording it is what the previous
    `(head, checkpoint)` pair could not do, and its absence is why an abort left HEAD detached.
    """

    branch: str | None
    head: str
    checkpoint: str


def checkpoint_worktree(repo: Path) -> WorktreeCheckpoint:
    """Checkpoint the worktree for a promotion transaction.

    A dirty tree (accumulated, not-yet-saved prior work) is committed with the
    service identity so a later ``reset --hard`` to the checkpoint cannot destroy
    it; a clean tree checkpoints as HEAD itself. ``.arch/`` runtime state is never
    staged (same pathspec rule as every other enterprise commit).
    """
    head = current_commit(repo)
    if head is None:
        raise RuntimeError("Cannot checkpoint enterprise worktree: no HEAD commit")
    # `current_branch` already answers None for a detached HEAD; re-checking for the literal "HEAD"
    # here would be a second reading of a rule its owner enforces.
    branch = current_branch(repo)
    if not has_uncommitted_changes(repo):
        return WorktreeCheckpoint(branch=branch, head=head, checkpoint=head)
    rc, _, stderr = run_repo_git(repo, *STAGE_ALL_BUT_RUNTIME_STATE)
    if rc != 0:
        raise RuntimeError(f"Failed to stage enterprise worktree for checkpoint: {stderr}")
    rc, _, stderr = commit_with_identity(repo, "promotion checkpoint (transient)", author=None)
    if rc != 0:
        raise RuntimeError(f"Failed to create promotion checkpoint commit: {stderr}")
    checkpoint = current_commit(repo)
    if checkpoint is None:
        raise RuntimeError("Promotion checkpoint commit did not produce a HEAD")
    return WorktreeCheckpoint(branch=branch, head=head, checkpoint=checkpoint)


def restore_worktree_checkpoint(repo: Path, checkpoint: WorktreeCheckpoint) -> None:
    """Abort path: return the worktree to its exact pre-checkpoint state.

    Four steps, and the first two are the ones a reset alone cannot do. Any operation git is still
    part-way through is aborted through git's own abort, which is what knows how to put the branch
    and the index back; the recorded branch is then reattached, because a reset moves commits and
    never HEAD's attachment.

    Then the original three: ``reset --hard`` to the checkpoint restores every tracked file;
    ``clean`` removes everything the promotion left untracked (``.arch/`` excepted — it is runtime
    state and was never part of the checkpoint); the final ``reset`` moves HEAD back so prior work is
    uncommitted again, exactly as before ``begin``.
    """
    _abandon_any_operation_in_progress(repo)
    _reattach(repo, checkpoint.branch)

    rc, _, stderr = run_repo_git(repo, "reset", "--hard", checkpoint.checkpoint)
    if rc != 0:
        raise RuntimeError(f"Failed to reset enterprise worktree to promotion checkpoint: {stderr}")
    rc, _, stderr = run_repo_git(repo, "clean", "-fd", "--", ".", ":(exclude).arch")
    if rc != 0:
        raise RuntimeError(f"Failed to clean enterprise worktree after promotion abort: {stderr}")
    if checkpoint.checkpoint != checkpoint.head:
        rc, _, stderr = run_repo_git(repo, "reset", "--mixed", checkpoint.head)
        if rc != 0:
            raise RuntimeError(f"Failed to restore enterprise HEAD after promotion abort: {stderr}")


def _abandon_any_operation_in_progress(repo: Path) -> None:
    """Unwind a rebase, cherry-pick, revert or merge git is still in the middle of.

    Through git's own abort rather than by deleting state directories: the abort restores the
    original HEAD, the index and the branch together, and a directory removed by hand leaves the
    index half-way through a replay that nothing will finish.

    Silent when there is nothing in progress, which is the ordinary case — this runs on every abort,
    not only after the operations that can leave state behind.
    """
    rc, git_dir, _ = run_repo_git(repo, "rev-parse", "--git-dir")
    if rc != 0:
        return
    root = (repo / git_dir).resolve() if not Path(git_dir).is_absolute() else Path(git_dir)
    for marker, abort in _IN_PROGRESS:
        if (root / marker).exists():
            rc, _, stderr = run_repo_git(repo, *abort)
            if rc != 0:
                raise RuntimeError(
                    f"Failed to abort the {abort[0]} in progress before restoring the enterprise "
                    f"worktree: {stderr}"
                )
            logger.warning("Aborted an in-progress %s while restoring the enterprise worktree", abort[0])
            return


def _reattach(repo: Path, branch: str | None) -> None:
    """Put HEAD back on the recorded branch, if it is not there already.

    A detached HEAD is the state that made this defect expensive rather than merely untidy:
    `submission_preflight` refuses one, so every submission, save and discard fails until someone
    intervenes by hand. `--force` because the tree at this point is whatever the failed operation
    left, and the reset below is about to replace it wholesale.
    """
    if branch is None or current_branch(repo) == branch:
        return
    rc, _, stderr = run_repo_git(repo, "checkout", "--force", branch)
    if rc != 0:
        raise RuntimeError(f"Failed to return the enterprise worktree to branch '{branch}': {stderr}")


def release_worktree_checkpoint(repo: Path, checkpoint: WorktreeCheckpoint) -> None:
    """Success path: un-commit the transient checkpoint, keeping the tree as is,
    so prior work AND the promotion's writes are unsaved changes again — the
    accumulate-then-save lifecycle owns the actual commit."""
    if checkpoint.checkpoint == checkpoint.head:
        return
    rc, _, stderr = run_repo_git(repo, "reset", "--mixed", checkpoint.head)
    if rc != 0:
        raise RuntimeError(f"Failed to release promotion checkpoint: {stderr}")




# ── Pinned checkpoints ────────────────────────────────────────────────────────────────────────────
#
# A promotion's checkpoint lives exactly as long as the transaction: it is a commit on the branch,
# un-committed again on release. A data upgrade needs the opposite — a checkpoint that outlives the
# run, so a later `--restore` can put the tree back after the software itself has moved on. That is a
# **ref**: `refs/arch-repair/pre-upgrade/<name>` holds a commit, and a commit a ref names survives
# `git gc`, is never pushed (no fetch or push spec names this namespace) and never moves the branch.
#
# One ref can name one commit, and a restore needs three facts — the tree, the head the branch was at,
# and the branch's name. So the pinned commit is made for the purpose: `commit-tree` over the
# checkpoint's tree, parented on the recorded head, with `Head:` and `Branch:` trailers in its message.
# Reading the pin reads those trailers; nothing else in the repository is consulted.

PINNED_CHECKPOINT_NAMESPACE = "refs/arch-repair/pre-upgrade"
_HEAD_TRAILER = "Head:"
_BRANCH_TRAILER = "Branch:"
_DETACHED = "(detached)"


def pin_checkpoint(repo: Path, checkpoint: WorktreeCheckpoint, name: str) -> str:
    """Record *checkpoint* under `refs/arch-repair/pre-upgrade/<name>`; returns the ref.

    The branch is left exactly where `checkpoint_worktree` left it — pinning writes objects and a
    ref, nothing in the working tree or on the branch — so the caller still releases the transient
    checkpoint commit afterwards, as a promotion does.
    """
    from src.config.git_identity import load_service_git_identity  # noqa: PLC0415

    service = load_service_git_identity()
    message = "\n".join([
        "arch-repair pre-upgrade checkpoint",
        "",
        f"{_HEAD_TRAILER} {checkpoint.head}",
        f"{_BRANCH_TRAILER} {checkpoint.branch or _DETACHED}",
    ])
    env = {
        "GIT_AUTHOR_NAME": service.name, "GIT_AUTHOR_EMAIL": service.email,
        "GIT_COMMITTER_NAME": service.name, "GIT_COMMITTER_EMAIL": service.email,
    }
    rc, pinned, stderr = run_repo_git(
        repo, "commit-tree", f"{checkpoint.checkpoint}^{{tree}}", "-p", checkpoint.head, "-m", message,
        env_overrides=env,
    )
    if rc != 0:
        raise RuntimeError(f"Failed to write the pinned checkpoint commit: {stderr}")
    ref = f"{PINNED_CHECKPOINT_NAMESPACE}/{name}"
    rc, _, stderr = run_repo_git(repo, "update-ref", ref, pinned.strip())
    if rc != 0:
        raise RuntimeError(f"Failed to pin the checkpoint under {ref}: {stderr}")
    return ref


def checkpoint_from_ref(repo: Path, ref: str) -> WorktreeCheckpoint:
    """The checkpoint a pinned ref records, in the form `restore_worktree_checkpoint` takes."""
    rc, pinned, stderr = run_repo_git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if rc != 0 or not pinned.strip():
        raise RuntimeError(f"No pinned checkpoint at {ref}: {stderr or 'ref not found'}")
    rc, body, stderr = run_repo_git(repo, "log", "-1", "--format=%B", pinned.strip())
    if rc != 0:
        raise RuntimeError(f"Failed to read the pinned checkpoint {ref}: {stderr}")
    head: str | None = None
    branch: str | None = None
    for line in body.splitlines():
        if line.startswith(_HEAD_TRAILER):
            head = line[len(_HEAD_TRAILER):].strip()
        elif line.startswith(_BRANCH_TRAILER):
            recorded = line[len(_BRANCH_TRAILER):].strip()
            branch = None if recorded == _DETACHED else recorded
    if head is None:
        raise RuntimeError(f"The pinned checkpoint {ref} records no head to return to")
    return WorktreeCheckpoint(branch=branch, head=head, checkpoint=pinned.strip())


def release_pinned_checkpoint(repo: Path, ref: str) -> None:
    """Forget a pinned checkpoint. Its objects become collectable; nothing else changes."""
    rc, _, stderr = run_repo_git(repo, "update-ref", "-d", ref)
    if rc != 0 and "not a valid ref" not in stderr and "does not exist" not in stderr:
        raise RuntimeError(f"Failed to release the pinned checkpoint {ref}: {stderr}")
