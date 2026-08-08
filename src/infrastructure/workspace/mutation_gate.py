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
from typing import Iterator

from src.application.mutation_authorization import GateBlock
from src.infrastructure.artifact_index._rwlock import current_thread_holds_index_write

#: What the gate can refuse for. The same alias the authorization policy uses, not a second copy:
#: this module re-declared the identical two-value Literal under its own name, so adding a third
#: block reason would have meant remembering both — and the REST layer's retryability set listed the
#: values as bare strings besides.
BlockReason = GateBlock


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
        self._writers_waiting: int = 0
        self._block_reason: BlockReason | None = None

    @contextmanager
    def _counted_as_waiting(self) -> Iterator[None]:
        """Make this waiter visible to readers, which yield while any writer waits.

        Only the bookkeeping is shared: each write path keeps its own wait condition, because
        ``writing()`` must also abandon the wait when a block reason appears and
        ``privileged_writing()`` must not. Caller holds ``self._cond``.
        """
        self._writers_waiting += 1
        try:
            yield
        finally:
            self._writers_waiting -= 1

    @contextmanager
    def writing(self) -> Iterator[None]:
        """Acquire exclusive WRITE.  Raises ``GateRejected`` if blocked."""
        _check_lock_order()
        with self._cond:
            if self._block_reason is not None:
                raise GateRejected(self._block_reason)
            with self._counted_as_waiting():
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
        """Acquire shared READ.  Waits for an in-progress WRITE, and for any waiting one.

        Order-checked like the write paths: a thread holding the index lock and then asking for the
        gate is the inversion, whichever gate mode it asks for.

        Yielding to ``_writers_waiting`` is what makes a writer reachable at all. Waiting only on
        ``_writing`` let overlapping readers hold ``_readers > 0`` continuously, and the old release
        notified only when the count reached zero — so under sustained read load a writer was not
        merely treated unfairly, it was never woken.
        """
        _check_lock_order()
        with self._cond:
            while self._writing or self._writers_waiting > 0:
                self._cond.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._cond:
                self._readers -= 1
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
        _check_lock_order()
        with self._cond:
            with self._counted_as_waiting():
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
    def is_writing(self) -> bool:
        """Whether a write is in progress right now.

        Exists so that code nested *inside* a write can assert it really is — whole-repository
        verification runs inside `gate.writing()` on the promote and cascade-delete paths, and that
        nesting is the reason it must never acquire for itself. A test asserting "verification
        completed" proves nothing on its own: it passes just as well if the nesting quietly goes
        away, and then the deadlock it guards against is no longer being guarded.

        A momentary answer, deliberately: it is a statement about the instant it was asked, useful
        for an assertion or a diagnostic, and useless for deciding whether to acquire — which is what
        `writing()` and `reading()` are for.
        """
        with self._cond:
            return self._writing

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

def _check_lock_order() -> None:
    """Assert that this thread does not already hold an index write.

    The documented order is **gate → index**; taking the gate while holding the index lock is the
    inversion that deadlocks. The answer comes from the locks themselves
    (``current_thread_holds_index_write``) rather than from a thread-local mirror: a mirror is a
    second copy of state the lock already owns, and it failed in two ways a single source cannot —
    a missed clear poisoned a pooled worker for every later unrelated task, and ownership split
    across threads read a clean flag and passed a genuine inversion.

    Guards every gate acquisition, not only ``writing()``: ``privileged_writing()`` is a write path
    too, and ``reading()`` became one that matters once verification began taking READ.
    """
    if current_thread_holds_index_write():
        raise AssertionError(
            "Lock order violation: the workspace gate was requested while this thread "
            "already holds ArtifactIndex._lock.writing().  Required order is gate → index."
        )



# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

_gate: WorkspaceMutationGate = WorkspaceMutationGate()


def get_workspace_gate() -> WorkspaceMutationGate:
    """Return the process-level workspace mutation gate."""
    return _gate


def _reset_for_test() -> None:
    """Replace the singleton with a fresh gate.  Tests only.

    Nothing else to reset: ownership lives in the index locks, so there is no mirror that could
    survive a test and poison the next one.
    """
    global _gate
    _gate = WorkspaceMutationGate()
