"""Connection acquisition and transaction framing for the signal-snapshot store.

Made an explicit collaborator rather than private methods on the adapter. The
snapshot operations are split across several modules by concern, and each of them
needs a connection; passing this object states that dependency instead of having
each module reach into the adapter's protected members.

Opening also applies the PRAGMAs and brings the schema current, so no caller can
work with a half-configured connection.
"""

from __future__ import annotations

from typing import Any, Callable

from src.domain.assurance.signals_schema import SIGNALS_PRAGMAS_SQL
from src.infrastructure.assurance._signals_migrations import apply_signals_migrations


class SnapshotConnection:
    """Works over any DB-API connection factory returning a row-dict connection
    (co-located SQLCipher in production; plain SQLite in the deprecated public
    backend's migration tests)."""

    def __init__(self, conn_factory: Callable[[], Any]) -> None:
        self._conn_factory = conn_factory

    def open(self) -> Any:
        conn = self._conn_factory()
        if conn is None:
            raise RuntimeError("Assurance store is locked — cannot access signal snapshots.")
        conn.executescript(SIGNALS_PRAGMAS_SQL)
        apply_signals_migrations(conn)
        return conn

    def begin(self, conn: Any) -> None:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except Exception:  # noqa: BLE001 — an implicit transaction is already open
            pass
