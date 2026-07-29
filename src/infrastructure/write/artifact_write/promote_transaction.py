"""Promotion write transactions: how a failed promotion leaves no trace.

Two strategies implement one contract:

* :class:`GitWorktreeTransaction` — the production strategy. Promotion runs on the
  enterprise working branch (``ensure_working_branch``); ``begin`` checkpoints the
  worktree (committing any accumulated-but-unsaved prior work so it is protected),
  ``abort`` resets the branch to the checkpoint and removes everything untracked
  except the ``.arch/`` runtime state, ``commit`` un-commits the checkpoint again so
  prior work stays "unsaved" exactly as the accumulate-then-save lifecycle expects.
  A reset cannot leave partial state; a file-restore loop can.

* :class:`FileBackupTransaction` — for callers whose enterprise root is not a git
  checkout (unit tests, ad-hoc roots). Restores the recorded per-file backups in
  reverse order and unlinks copied files. This is the historical mechanism; it
  cannot undo writes nobody backed up, which is precisely why the git strategy
  exists for the real workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.infrastructure.write.artifact_write._promote_file_ops import rollback


class PromotionTransaction(Protocol):
    """Bracket for the enterprise-side writes of one promotion execution."""

    def begin(self) -> None: ...

    def commit(self) -> None: ...

    def abort(self) -> None: ...


@dataclass
class FileBackupTransaction:
    """Restore per-file backups on abort; no-op bracket otherwise.

    ``copied`` and ``backups`` are the live lists the execution appends to —
    the transaction reads them only at abort time.
    """

    copied: list[Path]
    backups: list[tuple[Path, bytes | None]]

    def begin(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def abort(self) -> None:
        rollback(self.copied, self.backups)


@dataclass
class GitWorktreeTransaction:
    """Checkpoint/reset bracket on the enterprise working branch."""

    enterprise_root: Path
    _head: str | None = None
    _checkpoint: str | None = None

    def begin(self) -> None:
        from src.infrastructure.git.enterprise_git_ops import checkpoint_worktree  # noqa: PLC0415

        self._head, self._checkpoint = checkpoint_worktree(self.enterprise_root)

    def commit(self) -> None:
        from src.infrastructure.git.enterprise_git_ops import release_worktree_checkpoint  # noqa: PLC0415

        if self._head is not None and self._checkpoint is not None:
            release_worktree_checkpoint(self.enterprise_root, head=self._head, checkpoint=self._checkpoint)

    def abort(self) -> None:
        from src.infrastructure.git.enterprise_git_ops import restore_worktree_checkpoint  # noqa: PLC0415

        if self._head is None or self._checkpoint is None:
            raise RuntimeError("GitWorktreeTransaction.abort called before begin")
        restore_worktree_checkpoint(self.enterprise_root, head=self._head, checkpoint=self._checkpoint)
