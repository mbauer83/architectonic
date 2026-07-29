"""Process-level coarse RW gate for all model mutators.

Replaces the TOCTOU set in write_block_manager with a proper readers-writer
lock.  All mutators take WRITE; filesystem-dependent reads take READ; pure
index queries bypass the gate entirely.

Lock order: gate -> ArtifactIndex._lock.  Never acquire the index lock and
then the gate on the same thread — that ordering will deadlock.  The gate
detects this via a thread-local flag set by ArtifactIndex._lock.writing().
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator, Literal

BlockReason = Literal["sync_in_progress", "read_only"]


class GateRejected(Exception):
    """Raised when a mutator cannot take WRITE because the gate is blocked."""

    def __init__(self, reason: BlockReason) -> None:
        self.reason = reason
        super().__init__(f"Write rejected: {reason}")


class WorkspaceMutationGate:
    """Per-workspace coarse RW gate.

    All mutators acquire ``writing()``.  Filesystem-dependent reads acquire
    ``reading()`` so they observe a consistent snapshot across multi-file
    writes.  Pure index reads bypass the gate.

    Block reasons disable ``writing()`` for external callers:

    * ``sync_in_progress`` — a git pull is running; writes get 423-Retry-After.
    * ``read_only``        — workspace is in read-only mode; all writes blocked.

    The sync publisher uses ``privileged_writing()`` to hold WRITE during the
    M4 publish window while ``sync_in_progress`` is still set.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._readers: int = 0
        self._writing: bool = False
        self._block_reason: BlockReason | None = None

    @contextmanager
    def writing(self) -> Iterator[None]:
        """Acquire exclusive WRITE.  Raises ``GateRejected`` if blocked."""
        _check_lock_order()
        with self._cond:
            if self._block_reason is not None:
                raise GateRejected(self._block_reason)
            while self._writing or self._readers > 0:
                self._cond.wait()
                if self._block_reason is not None:
                    raise GateRejected(self._block_reason)
            self._writing = True
        try:
            yield
        finally:
            with self._cond:
                self._writing = False
                self._cond.notify_all()

    @contextmanager
    def reading(self) -> Iterator[None]:
        """Acquire shared READ.  Waits for any in-progress WRITE to finish."""
        with self._cond:
            while self._writing:
                self._cond.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._cond:
                self._readers -= 1
                if self._readers == 0:
                    self._cond.notify_all()

    @contextmanager
    def blocking_writes(self, reason: BlockReason) -> Iterator[None]:
        """Set block reason, flushing any in-progress writer first.

        External ``writing()`` calls raise ``GateRejected`` immediately while
        this context is active.  The sync publisher can still call
        ``privileged_writing()`` inside this scope.
        """
        with self._cond:
            while self._writing:
                self._cond.wait()
            self._block_reason = reason
        try:
            yield
        finally:
            with self._cond:
                self._block_reason = None
                self._cond.notify_all()

    @contextmanager
    def privileged_writing(self) -> Iterator[None]:
        """Acquire exclusive WRITE even when a block reason is set.

        For the sync publisher's M4 publish window only.  The block reason
        remains active so external mutators continue to receive ``GateRejected``.
        """
        with self._cond:
            while self._writing or self._readers > 0:
                self._cond.wait()
            self._writing = True
        try:
            yield
        finally:
            with self._cond:
                self._writing = False
                self._cond.notify_all()

    @property
    def block_reason(self) -> BlockReason | None:
        with self._cond:
            return self._block_reason

    def set_block(self, reason: BlockReason) -> None:
        """Directly set the block reason.  Compat shim for write_block_manager."""
        with self._cond:
            self._block_reason = reason
            self._cond.notify_all()

    def clear_block(self) -> None:
        """Clear the block reason.  Compat shim for write_block_manager."""
        with self._cond:
            self._block_reason = None
            self._cond.notify_all()


# ---------------------------------------------------------------------------
# Lock-order enforcement
# ---------------------------------------------------------------------------

_tl = threading.local()


def _check_lock_order() -> None:
    """Assert that this thread does not already hold ArtifactIndex._lock.writing().

    Called at the top of writing() to detect reversed lock acquisition.
    ArtifactIndex._lock.writing() sets ``_tl.holding_index_write`` via the
    import below.
    """
    if getattr(_tl, "holding_index_write", False):
        raise AssertionError(
            "Lock order violation: gate.writing() called while this thread "
            "already holds ArtifactIndex._lock.writing().  "
            "Required order: gate → index."
        )


def _mark_index_write_held(held: bool) -> None:
    """Called by ArtifactIndex._lock to record when this thread holds index WRITE."""
    _tl.holding_index_write = held


# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

_gate: WorkspaceMutationGate = WorkspaceMutationGate()


def get_workspace_gate() -> WorkspaceMutationGate:
    """Return the process-level workspace mutation gate."""
    return _gate


def _reset_for_test() -> None:
    """Replace the singleton with a fresh gate.  Tests only."""
    global _gate
    _gate = WorkspaceMutationGate()
    _tl.holding_index_write = False
