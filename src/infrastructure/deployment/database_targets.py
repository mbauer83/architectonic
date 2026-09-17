"""Database operational targets: the public signals SQLite file and the
co-located SQLCipher assurance store.

Migrations run through one explicit transactional migration connection per
target — never through a store adapter (whose constructors/bootstrap must not
auto-create current tables ahead of detection). The SQLCipher key comes only
from the established non-interactive credential store; it never appears in
reports or logs.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.repository.operational_upgrade import UpgradeTarget

SIGNAL_SCHEMA_META_TABLE = "signal_schema_meta"
SIGNAL_SCHEMA_VERSION_KEY = "signal_schema_version"

ConnectionFactory = Callable[[], Any]


def signal_schema_version(conn: Any) -> int:
    """The stamped signal-table version; legacy stores without the table are 0."""
    try:
        row = conn.execute(
            f"SELECT value FROM {SIGNAL_SCHEMA_META_TABLE} WHERE key = ?",
            (SIGNAL_SCHEMA_VERSION_KEY,),
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    except Exception as exc:  # noqa: BLE001 — sqlcipher3 raises its own OperationalError type
        if "no such table" in str(exc):
            return 0
        raise
    return int(row[0]) if row else 0


@dataclass
class DatabaseUnitOfWork:
    """One migration transaction on one database target.

    Connections are opened in autocommit mode and the unit opens one explicit
    `BEGIN IMMEDIATE` transaction, so DDL participates in the rollback boundary
    (SQLite's transactional DDL) instead of silently auto-committing.
    """

    _conn: Any

    def __post_init__(self) -> None:
        self._conn.execute("BEGIN IMMEDIATE")

    def write_text(self, relative_path: str, content: str) -> None:
        raise NotImplementedError("database targets have no text surface")

    def execute_sql(self, sql: str, parameters: tuple[object, ...] = ()) -> None:
        self._conn.execute(sql, parameters)

    def commit(self) -> None:
        try:
            self._conn.execute("COMMIT")
        finally:
            self._conn.close()

    def rollback(self) -> None:
        try:
            self._conn.execute("ROLLBACK")
        finally:
            self._conn.close()


@dataclass(frozen=True)
class _DatabaseView:
    target: UpgradeTarget
    connect: ConnectionFactory

    def read_text(self, relative_path: str = "") -> str | None:
        return None

    def list_files(self, relative_glob: str) -> list[str]:
        return []

    def query_scalar(self, sql: str, parameters: tuple[object, ...] = ()) -> object | None:
        conn = self.connect()
        try:
            row = conn.execute(sql, parameters).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def query_column(self, sql: str, parameters: tuple[object, ...] = ()) -> list[object]:
        conn = self.connect()
        try:
            return [row[0] for row in conn.execute(sql, parameters).fetchall()]
        finally:
            conn.close()


@dataclass(frozen=True)
class DatabaseTargetHandle:
    """One discovered database target bound to its migration-connection factory."""

    target: UpgradeTarget
    connect: ConnectionFactory
    inspectable: bool
    #: Where the database file is, for the file-level copy a backup is. None only for a handle a
    #: test builds around a connection with no file behind it; such a handle has nothing to back up.
    path: Path | None = None

    def view(self) -> _DatabaseView:
        return _DatabaseView(self.target, self.connect)

    def begin(self) -> DatabaseUnitOfWork:
        return DatabaseUnitOfWork(self.connect())

    def backup(self, destination_dir: Path) -> Path | None:
        """A file copy with its write-ahead log — the same copy `arch-assurance backup` takes.

        Through that one function rather than a second `copy2`, because the log is the point: a
        WAL-mode store's latest commits live in `<db>-wal` until a checkpoint, and a copy of the
        main file alone is a snapshot from before them. An encrypted store stays encrypted; the key
        is never read here.
        """
        if self.path is None or not self.path.is_file():
            return None
        from src.infrastructure.assurance.lifecycle import backup_store  # noqa: PLC0415

        destination_dir.mkdir(parents=True, exist_ok=True)
        copy = destination_dir / self.path.name
        backup_store(self.path, backup_path=copy)
        return copy

    def restore(self, backup: Path) -> None:
        """Put the file (and its log) back; a stale `-shm` is scratch state SQLite rebuilds."""
        if self.path is None:
            raise RuntimeError(f"{self.target.display_location}: no file to restore into")
        for sidecar in ("-wal", "-shm"):
            self.path.with_name(self.path.name + sidecar).unlink(missing_ok=True)
        shutil.copy2(backup, self.path)
        wal = backup.with_name(backup.name + "-wal")
        if wal.exists():
            shutil.copy2(wal, self.path.with_name(self.path.name + "-wal"))


def sqlite_connection_factory(path: Path) -> ConnectionFactory:
    """Connections that never create an absent file (discovery only hands out
    handles for present files; `mode=rw` keeps that invariant at the driver)."""

    def connect() -> Any:
        return sqlite3.connect(f"file:{path}?mode=rw", uri=True, isolation_level=None)

    return connect


def sqlcipher_connection_factory(path: Path, key: str) -> ConnectionFactory:
    """Raw credential-bearing migration connections — no store bootstrap runs."""

    def connect() -> Any:
        import sqlcipher3  # type: ignore[import-untyped]  # noqa: PLC0415

        conn = sqlcipher3.connect(str(path), isolation_level=None)
        conn.execute(f"PRAGMA key = '{key}'")
        return conn

    return connect


def sqlcipher_readable(factory: ConnectionFactory) -> bool:
    """True when the key actually opens the store (wrong/absent key fails closed)."""
    try:
        conn = factory()
    except Exception:  # noqa: BLE001
        return False
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        conn.close()
