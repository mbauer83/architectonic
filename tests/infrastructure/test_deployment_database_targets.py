"""Database operational targets: version probing, migration transactions, and the
never-create-an-absent-file invariant."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.domain.repository.operational_upgrade import UpgradeTarget
from src.infrastructure.deployment.database_targets import (
    SIGNAL_SCHEMA_META_TABLE,
    DatabaseTargetHandle,
    signal_schema_version,
    sqlcipher_connection_factory,
    sqlcipher_readable,
    sqlite_connection_factory,
)


def _target(location: str) -> UpgradeTarget:
    return UpgradeTarget(
        kind="signals_sqlite",
        stable_id=f"signals_sqlite:{location}",
        display_location=location,
        current_version=None,
    )


def _legacy_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE boms (id INTEGER PRIMARY KEY, serial TEXT)")
    conn.commit()
    conn.close()


class TestVersionProbe:
    def test_legacy_store_without_meta_table_is_version_zero(self, tmp_path: Path) -> None:
        db = tmp_path / "signals.db"
        _legacy_db(db)
        conn = sqlite3.connect(db)
        assert signal_schema_version(conn) == 0
        conn.close()

    def test_stamped_version_is_read_back(self, tmp_path: Path) -> None:
        db = tmp_path / "signals.db"
        conn = sqlite3.connect(db)
        conn.execute(f"CREATE TABLE {SIGNAL_SCHEMA_META_TABLE} (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            f"INSERT INTO {SIGNAL_SCHEMA_META_TABLE} VALUES ('signal_schema_version', '1')"
        )
        conn.commit()
        conn.close()
        conn = sqlite3.connect(db)
        assert signal_schema_version(conn) == 1
        conn.close()


class TestSqliteFactory:
    def test_never_creates_an_absent_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.db"
        factory = sqlite_connection_factory(missing)
        with pytest.raises(sqlite3.OperationalError):
            factory()
        assert not missing.exists()

    def test_migration_transaction_commits_or_rolls_back_whole(self, tmp_path: Path) -> None:
        db = tmp_path / "signals.db"
        _legacy_db(db)
        handle = DatabaseTargetHandle(
            target=_target(str(db)), connect=sqlite_connection_factory(db), inspectable=True
        )
        uow = handle.begin()
        uow.execute_sql("CREATE TABLE extra (id INTEGER)")
        uow.rollback()
        conn = sqlite3.connect(db)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        conn.close()
        assert "extra" not in tables

        uow = handle.begin()
        uow.execute_sql("CREATE TABLE extra (id INTEGER)")
        uow.commit()
        conn = sqlite3.connect(db)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        conn.close()
        assert "extra" in tables

    def test_view_query_scalar(self, tmp_path: Path) -> None:
        db = tmp_path / "signals.db"
        _legacy_db(db)
        handle = DatabaseTargetHandle(
            target=_target(str(db)), connect=sqlite_connection_factory(db), inspectable=True
        )
        assert handle.view().query_scalar("SELECT count(*) FROM boms") == 0

    def test_view_query_column_returns_every_row(self, tmp_path: Path) -> None:
        """The scalar read answers one value; a step that migrates rows has to see them all.
        Standing in for this with LIMIT/OFFSET scalars re-runs the query per row and cannot tell
        an empty set from a NULL."""
        db = tmp_path / "signals.db"
        _legacy_db(db)
        conn = sqlite3.connect(db)
        conn.executemany("INSERT INTO boms (serial) VALUES (?)", [("one",), ("two",)])
        conn.commit()
        conn.close()
        handle = DatabaseTargetHandle(
            target=_target(str(db)), connect=sqlite_connection_factory(db), inspectable=True
        )

        assert sorted(handle.view().query_column("SELECT serial FROM boms")) == ["one", "two"]

    def test_view_query_column_is_empty_for_no_rows(self, tmp_path: Path) -> None:
        db = tmp_path / "signals.db"
        _legacy_db(db)
        handle = DatabaseTargetHandle(
            target=_target(str(db)), connect=sqlite_connection_factory(db), inspectable=True
        )

        assert handle.view().query_column("SELECT serial FROM boms") == []


class TestSqlcipherFactory:
    def test_wrong_key_fails_closed(self, tmp_path: Path) -> None:
        sqlcipher3 = pytest.importorskip("sqlcipher3")
        db = tmp_path / "store.db"
        conn = sqlcipher3.connect(str(db))
        conn.execute("PRAGMA key = 'right-key'")
        conn.execute("CREATE TABLE nodes (id TEXT)")
        conn.commit()
        conn.close()

        assert sqlcipher_readable(sqlcipher_connection_factory(db, "right-key"))
        assert not sqlcipher_readable(sqlcipher_connection_factory(db, "wrong-key"))

    def test_version_zero_on_legacy_encrypted_store(self, tmp_path: Path) -> None:
        sqlcipher3 = pytest.importorskip("sqlcipher3")
        db = tmp_path / "store.db"
        conn = sqlcipher3.connect(str(db))
        conn.execute("PRAGMA key = 'k'")
        conn.execute("CREATE TABLE boms (id TEXT)")
        conn.commit()
        conn.close()
        factory = sqlcipher_connection_factory(db, "k")
        conn = factory()
        assert signal_schema_version(conn) == 0
        conn.close()
