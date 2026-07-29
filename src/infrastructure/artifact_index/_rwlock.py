"""Simple readers-writer lock for the artifact index.

Allows concurrent readers and exclusive writers. No writer priority — this is
intentional: writes are rare (user-triggered or 5-minute periodic refresh) so
write starvation is not a practical risk, and avoiding writer priority prevents
reads from being blocked whenever any write is queued.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


class _RWLock:
    """Allows concurrent reads, exclusive writes."""

    def __init__(self) -> None:
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0
        self._writing = False

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
        try:
            from src.infrastructure.workspace.mutation_gate import _mark_index_write_held  # noqa: PLC0415
            _mark_index_write_held(True)
        except ImportError:
            pass
        try:
            yield
        finally:
            try:
                from src.infrastructure.workspace.mutation_gate import _mark_index_write_held  # noqa: PLC0415
                _mark_index_write_held(False)
            except ImportError:
                pass
            with self._cond:
                self._writing = False
                self._cond.notify_all()
