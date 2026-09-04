"""A throwaway checkout to attempt something in, so a failure never touches what a reader is looking at.

A rebase has to be *attempted* to know whether it applies. Attempting it in the enterprise checkout
means a conflict leaves its state there — which is how a failed rehearsal came to take down every
submission, save and discard until someone intervened by hand.

**A real `git worktree`, not the staged workspace and not the checkpoint bracket.** Both alternatives
were ruled out from the code rather than by experiment:

* `create_staging_repo` builds a mirror whose root is a bare `mkdir` with read-through interception.
  There is no `.git` in it, so `git rebase` cannot run there at all.
* `GitWorktreeTransaction` is named for a worktree and is not one — it operates in place on the
  enterprise root, and its abort is a reset. It now recovers from an operation in progress, which is
  worth having regardless, but recovering is not the same as never touching the checkout.

A worktree shares the object database and has its own index, HEAD and working directory. Whatever a
rehearsal does to those, the enterprise checkout does not see.

**Interrupted runs are cleaned up on startup, not only on exit.** A killed process leaves the
directory gone but the administrative entry behind, and git then refuses to create the next worktree
at a path it still believes is registered. `prune_stale_worktrees` is the standing repair.

**`git_sync_m4` has async siblings** — `add_detached_worktree` and `prepare_rebase_worktree`, which
already rebases in an isolated worktree and tells a conflict from a failure. They are not merged with
these, and the reason is not stylistic: those run inside the sync manager's event loop and take an
awaitable runner, while a rehearsal runs in the write-queue executor thread, where awaiting is not
available. Bridging the two would mean blocking the loop or threading a runner through both, which
buys less than it costs for three command shapes.

What *was* shared is the repair: `prune_stale_worktrees` forgets any worktree git reports as
prunable, so an interrupted sync worktree under `.arch-repo/sync-worktrees/` is cleaned up by the same
startup pass. Nothing pruned those before.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from src.infrastructure.git._git_command import run_repo_git

logger = logging.getLogger(__name__)

#: Names the temporary directory so a person reading a `/tmp` listing can see whose it is. It is not
#: a filter: pruning asks git what is prunable rather than matching on a name, so a worktree someone
#: made by hand and still has on disk is never touched whatever it is called.
REHEARSAL_PREFIX = "arch-rehearsal-"


class RehearsalUnavailable(RuntimeError):
    """A rehearsal worktree could not be created, so nothing was attempted."""


@dataclass(frozen=True, slots=True)
class Rehearsal:
    """A checkout to attempt something in, and the commit it starts from."""

    path: Path
    start_point: str


@contextmanager
def rehearsal_worktree(repo: Path, *, start_point: str) -> Iterator[Rehearsal]:
    """A worktree at `start_point`, removed however the block exits.

    Detached on purpose: a worktree that checked out a *branch* would lock it, and the branch a
    rehearsal is about is the one the enterprise checkout has. Two worktrees cannot hold the same
    branch, so attempting the rebase would refuse before it began.
    """
    parent = Path(tempfile.mkdtemp(prefix=REHEARSAL_PREFIX))
    path = parent / "worktree"
    rc, _, stderr = run_repo_git(repo, "worktree", "add", "--detach", str(path), start_point)
    if rc != 0:
        shutil.rmtree(parent, ignore_errors=True)
        raise RehearsalUnavailable(f"Could not create a rehearsal worktree at {start_point}: {stderr}")

    try:
        yield Rehearsal(path=path, start_point=start_point)
    finally:
        _remove(repo, path, parent)


def _remove(repo: Path, path: Path, parent: Path) -> None:
    """Take the worktree down three ways, because none of them alone is enough.

    Git's own removal first, so the administrative entry goes with the files. `--force` because a
    rehearsal is expected to leave the tree dirty — measured: `worktree remove` refuses a worktree
    with modified or untracked files, rc 128 — and without it every rehearsal that did its job would
    log a warning about a removal that then happened anyway.

    Then the temporary directory, because a `remove` that failed for some other reason would
    otherwise leave files accumulating over a long-running process. Then a prune, because a directory
    removed behind git's back leaves the entry that makes the *next* worktree at that path refuse.
    """
    rc, _, stderr = run_repo_git(repo, "worktree", "remove", "--force", str(path))
    if rc != 0:
        logger.warning("Could not remove the rehearsal worktree at %s: %s", path, stderr)
    shutil.rmtree(parent, ignore_errors=True)
    run_repo_git(repo, "worktree", "prune")


def prune_stale_worktrees(repo: Path) -> None:
    """Forget worktrees whose directories are gone — a rehearsal's, or a sync's.

    A killed process leaves the directory removed with the administrative entry behind, and git then
    refuses to create a worktree at a path it still believes is registered. So the *next* run fails
    because of the last one's interruption, which is a failure with no visible cause where it appears.

    Prunes what git itself reports as prunable, so a worktree a person created and still has on disk
    is never touched. Run at startup, where the other durable leftovers are settled.
    """
    rc, _, stderr = run_repo_git(repo, "worktree", "prune")
    if rc != 0:
        logger.warning("Could not prune worktrees in %s: %s", repo, stderr)
