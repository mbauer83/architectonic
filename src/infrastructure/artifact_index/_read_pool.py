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


class ReadConnectionPool:
    """Owns its connections, and is the only thing that opens or closes them."""

    def __init__(self, uri: str, size: int = READ_POOL_SIZE) -> None:
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
        """
        connection = self._connections.get()
        try:
            yield connection
        finally:
            self._connections.put(connection)

    def close(self) -> None:
        """Close every connection currently checked in. Idempotent.

        Drained by `get_nowait` rather than by count on purpose: a connection checked out at this
        moment belongs to its holder and is not ours to close underneath it. Dropping our reference
        lets it be collected once that holder is done.
        """
        with contextlib.suppress(queue.Empty):
            while True:
                self._connections.get_nowait().close()

    def size(self) -> int:
        """How many connections are checked in right now — for tests that assert the pool exists."""
        return self._connections.qsize()
