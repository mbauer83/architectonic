"""Thread-local SQLCipher connection management for the assurance store.

SQLite/SQLCipher connection objects are bound to the thread that created them, but
the store is a process singleton served from a pool of OS threads (the anyio
threadpool for sync REST handlers + FastMCP tool execution). This manager gives
each accessing thread its own lazily-opened, cached connection, opened in **WAL**
mode with a busy timeout so concurrent readers do not block one another or the
writer, and with the store's PRAGMAs applied — they are per-connection settings,
so a connection that skipped them would silently lose referential integrity. A
generation counter invalidates cached connections across lock/unlock
cycles; every open connection is tracked so ``close()`` disposes them all. The
encryption key is held in process memory only between ``open()`` and ``close()``.

Write *serialisation* (single-writer discipline) is a separate concern handled at
the MCP/REST boundary by the assurance write queue — this manager only guarantees
that any thread can safely obtain a connection.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from src.infrastructure.assurance._schema import ASSURANCE_PRAGMAS_SQL
from src.infrastructure.assurance._sqlcipher_util import dict_row_factory as _dict_row_factory

logger = logging.getLogger(__name__)

_BUSY_TIMEOUT_MS = 5000


class ThreadLocalConnectionManager:
    """Per-thread keyed WAL connections with generation-based invalidation."""

    def __init__(
        self,
        db_path: Path,
        *,
        bootstrap: Callable[[Any], None] | None = None,
        busy_timeout_ms: int = _BUSY_TIMEOUT_MS,
    ) -> None:
        self._db_path = db_path
        self._bootstrap = bootstrap
        self._busy_timeout_ms = busy_timeout_ms
        self._open = False
        self._key: str | None = None
        self._local = threading.local()
        self._mgmt_lock = threading.Lock()
        self._all_conns: list[Any] = []
        self._generation = 0

    def availability_revision(self) -> int:
        """Monotonic generation, bumped on every open/close (lock/unlock/rekey) —
        the inward-facing availability signal snapshot tokens pin against."""
        return self._generation

    def is_open(self) -> bool:
        return self._open

    def open(self, key: str) -> None:
        """Activate the manager with *key* and open the bootstrap connection."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._mgmt_lock:
            self._key = key
            self._generation += 1
            self._open = True
        conn = self._open_connection(bootstrap=True)
        self._local.conn = conn
        self._local.gen = self._generation
        logger.info("Assurance store connections opened at %s", self._db_path)

    def checkpoint(self) -> bool:
        """Fold the write-ahead log back into the database file. False when there is nothing open.

        WAL mode leaves committed pages in ``store.db-wal`` until something checkpoints. A clean
        close of the last connection does it; a SIGKILL does not — and this backend *has* been
        SIGKILLed, because ``--stop`` escalates when graceful shutdown hangs on an open event
        stream. Every unflushed page in the WAL at that moment is a committed write that the next
        open may discard.

        Best-effort by design: it is called on paths that must not fail because of it, including
        lifespan teardown, and a store that is locked simply has nothing to flush.
        """
        conn = self.get_or_none()
        if conn is None:
            return False
        try:
            # TRUNCATE rather than PASSIVE: it resets the log file, so a crash immediately after
            # finds no WAL to recover rather than one whose frames were already applied.
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:  # noqa: BLE001
            logger.warning("Assurance store WAL checkpoint failed", exc_info=True)
            return False
        return True

    def close(self) -> None:
        """Deactivate and dispose every open connection."""
        # Before the connections go: closing the last one would normally checkpoint, but only on a
        # clean close of every connection, and this manager hands one to each thread.
        self.checkpoint()
        with self._mgmt_lock:
            self._open = False
            self._key = None
            self._generation += 1
            conns, self._all_conns = self._all_conns, []
        for conn in conns:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        self._local.__dict__.pop("conn", None)
        logger.info("Assurance store connections closed")

    def get_or_none(self) -> Any:
        """The calling thread's connection, or None when the manager is closed."""
        if not self._open:
            return None
        local = self._local
        if getattr(local, "conn", None) is not None and getattr(local, "gen", None) == self._generation:
            return local.conn
        conn = self._open_connection(bootstrap=False)
        local.conn = conn
        local.gen = self._generation
        return conn

    def require(self) -> Any:
        conn = self.get_or_none()
        if conn is None:
            raise RuntimeError("Assurance store is locked. Run `arch-assurance unlock`.")
        return conn

    def _open_connection(self, *, bootstrap: bool) -> Any:
        import sqlcipher3  # type: ignore[import-untyped]

        key = self._key
        if key is None:
            raise RuntimeError("Assurance store is locked. Run `arch-assurance unlock`.")
        conn = sqlcipher3.connect(str(self._db_path), check_same_thread=False)
        conn.execute(f"PRAGMA key = '{key}'")
        conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        conn.executescript(ASSURANCE_PRAGMAS_SQL)
        conn.row_factory = _dict_row_factory
        if bootstrap and self._bootstrap is not None:
            try:
                self._bootstrap(conn)
            except Exception:
                conn.close()
                with self._mgmt_lock:
                    self._open = False
                    self._key = None
                raise
        with self._mgmt_lock:
            self._all_conns.append(conn)
        return conn
