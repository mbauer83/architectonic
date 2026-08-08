"""Simple readers-writer lock for the artifact index.

Allows concurrent readers and exclusive writers. No writer priority — this is
intentional: writes are rare (user-triggered or 5-minute periodic refresh) so
write starvation is not a practical risk, and avoiding writer priority prevents
reads from being blocked whenever any write is queued.
"""

from __future__ import annotations

import threading
import weakref
from contextlib import contextmanager
from typing import Iterator

#: Every live lock, so "does this thread hold an index write?" can be answered from the locks
#: themselves. A weak set: an index that goes away takes its lock's answer with it.
_LIVE_LOCKS: "weakref.WeakSet[_RWLock]" = weakref.WeakSet()


def current_thread_holds_index_write() -> bool:
    """Whether the calling thread is the writer of any live index lock.

    The single source of truth for lock-order enforcement. It replaces a thread-local flag that
    *mirrored* this state: the mirror was set and cleared by the same acquire/release pair, so a
    missed clear left a pooled worker permanently poisoned, and a lock acquired on one thread while
    the gate was requested on another read a clean flag and let a genuine inversion through. Asking
    the lock cannot diverge from what the lock knows.
    """
    ident = threading.get_ident()
    return any(lock.writer_ident == ident for lock in list(_LIVE_LOCKS))


class _RWLock:
    """Allows concurrent reads, exclusive writes."""

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0
        self._writing = False
        self._writer_ident: int | None = None
        _LIVE_LOCKS.add(self)

    @property
    def writer_ident(self) -> int | None:
        """The thread currently holding WRITE, or None. Read without the condition deliberately:
        an int assignment is atomic, and a caller asking "is it me?" cannot race with itself."""
        return self._writer_ident

    @contextmanager
    def reading(self) -> Iterator[None]:
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
    def writing(self) -> Iterator[None]:
        with self._cond:
            while self._writing or self._readers > 0:
                self._cond.wait()
            self._writing = True
            self._writer_ident = threading.get_ident()
        try:
            yield
        finally:
            with self._cond:
                self._writing = False
                self._writer_ident = None
                self._cond.notify_all()
