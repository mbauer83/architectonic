"""A fixed pool of SQLite read connections, checked out one per reader.

Extracted from `_SqliteStore`, which is about the index's SQL and had accreted the pool's lifecycle
alongside it: sizing, construction, check-out/check-in, and — once the store gained a `close()` —
draining. Four concerns about connections in a module about statements, and the file had grown past
its length baseline carrying them.

The reason a pool exists at all: every connection here opens the *same* shared-cache in-memory
database, so a reader sees the write connection's committed writes automatically, while SQLite's
SHARED locks can coexist and reads genuinely parallelise up to the pool's size. One connection shared
across threads would serialise them.
"""

from __future__ import annotations

import contextlib
import os
import queue
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

#: Enough to parallelise reads on a small machine without opening a connection per core on a large one.
READ_POOL_SIZE = min(max(os.cpu_count() or 4, 4), 8)

#: How long a check-out may wait before the wait is treated as a defect rather than as contention.
#:
#: A read holds a connection for microseconds and the pool has eight, so a wait of this length is not
#: a busy pool — it is a connection that is never coming back. Bounded because the alternative is
#: what this used to do: block forever, on a queue nothing will ever put to again.
_CHECKOUT_BUDGET_SECONDS = 60.0


class ReadPoolClosed(RuntimeError):
    """A read was asked of a pool whose connections have been released.

    `close()` drains the queue and keeps it drained, so a `get()` afterwards waits for a connection
    that cannot arrive. That is a use-after-close, and it presented as the worst possible symptom: a
    test blocked forever inside a search, its xdist worker silent, the controller waiting on it, and
    a whole run hanging near the end with no failure and no output. Named and raised so the caller
    that reuses a closed index is the thing that fails.
    """


class ReadConnectionPool:
    """Owns its connections, and is the only thing that opens or closes them."""

    def __init__(self, uri: str, size: int = READ_POOL_SIZE) -> None:
        self._closed = False
        self._connections: queue.Queue[sqlite3.Connection] = queue.Queue()
        for _ in range(size):
            connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            self._connections.put(connection)

    @contextmanager
    def reader(self) -> Generator[sqlite3.Connection, None, None]:
        """Check out a connection and return it on the way out, however the caller leaves.

        Must be called inside the index's `reading()` lock, so the write connection cannot be
        modifying tables while a pooled connection reads them.

        Raises rather than waits where no connection can arrive. The check-out is bounded as well as
        guarded, because `close()` can land between the two and leave the guard satisfied and the
        queue empty — and a race that ends in a hang is the failure this whole method exists to stop
        having.
        """
        connection = self._checked_out()
        try:
            yield connection
        finally:
            self._connections.put(connection)

    def _checked_out(self) -> sqlite3.Connection:
        if self._closed:
            raise ReadPoolClosed(
                "this index's read connections have been released; the index was closed and is "
                "being read again. Open a new index rather than reusing a closed one."
            )
        try:
            return self._connections.get(timeout=_CHECKOUT_BUDGET_SECONDS)
        except queue.Empty:
            raise ReadPoolClosed(
                "no read connection became available within "
                f"{_CHECKOUT_BUDGET_SECONDS:.0f}s. Either this index was closed while the read was "
                "waiting, or a connection was checked out and never returned."
            ) from None

    def close(self) -> None:
        """Close every connection currently checked in. Idempotent.

        Drained by `get_nowait` rather than by count on purpose: a connection checked out at this
        moment belongs to its holder and is not ours to close underneath it. Dropping our reference
        lets it be collected once that holder is done.

        The flag is what makes a later read fail instead of wait. Without it the queue is simply
        empty forever, which is indistinguishable — to `get()` — from a busy pool.
        """
        self._closed = True
        with contextlib.suppress(queue.Empty):
            while True:
                self._connections.get_nowait().close()

    def size(self) -> int:
        """How many connections are checked in right now — for tests that assert the pool exists."""
        return self._connections.qsize()
