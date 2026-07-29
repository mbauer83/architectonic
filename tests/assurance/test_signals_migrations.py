"""Signals schema migrations: explicit version table, ordered transactional
application, idempotency, one-active-snapshot DB constraint, replay-key uniqueness,
and finding uniqueness — on BOTH the public SQLite backend and the co-located
SQLCipher backend. The signal-snapshot aggregate is the sole signals model."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.domain.assurance.signals_schema import (
    SIGNALS_MIGRATIONS,
    SIGNALS_PRAGMAS_SQL,
    SNAPSHOT_TABLES_VERSION,
    signals_migration_statements,
)
from src.infrastructure.assurance._signals_migrations import (
    SIGNALS_SCHEMA_VERSION,
    SignalsSchemaUnsupportedError,
    apply_signals_migrations,
    signals_schema_version,
)


def _bring_to_version(conn: Any, target: int) -> None:
    """Apply the shipped migrations up to `target` and stamp it, leaving later ones unapplied.

    Built from the shipped migration list rather than a copied DDL string, so the fixture is the
    schema those versions really produced.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS signals_schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    for version, ddl in SIGNALS_MIGRATIONS:
        if version > target:
            break
        for statement in signals_migration_statements(ddl):
            conn.execute(statement)
    conn.execute(
        "INSERT OR REPLACE INTO signals_schema_meta(key, value) VALUES ('schema_version', ?)",
        (str(target),))
    conn.commit()


def _dict_row(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:  # type: ignore[type-arg]
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


def _sqlite_conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(tmp_path / "signals.db"))
    conn.row_factory = _dict_row  # type: ignore[assignment]
    conn.executescript(SIGNALS_PRAGMAS_SQL)
    conn.commit()
    return conn


def _sqlcipher_conn(tmp_path: Path) -> Any:
    pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "store.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    conn = store._thread_conn_or_none()  # noqa: SLF001 — the factory the store receives in production
    conn.executescript(SIGNALS_PRAGMAS_SQL)
    conn.commit()
    return conn


@pytest.fixture(params=["sqlite", "sqlcipher"])
def conn(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    if request.param == "sqlite":
        return _sqlite_conn(tmp_path)
    return _sqlcipher_conn(tmp_path)


class TestMigrationApplication:
    def test_fresh_schema_reports_baseline_then_migrates(self, conn: Any) -> None:
        assert signals_schema_version(conn) == 1
        assert apply_signals_migrations(conn) == SIGNALS_SCHEMA_VERSION
        assert signals_schema_version(conn) == SIGNALS_SCHEMA_VERSION

    def test_application_is_idempotent(self, conn: Any) -> None:
        apply_signals_migrations(conn)
        assert apply_signals_migrations(conn) == SIGNALS_SCHEMA_VERSION

    def test_pre_rename_store_raises_instead_of_failing_on_a_missing_table(
        self, conn: Any,
    ) -> None:
        """Regression: a store stamped as having the snapshot tables but carrying the
        pre-rename ones skips that migration, after which every query fails with an
        opaque ``no such table``. It must raise a typed, actionable error.

        Stamped at the version that introduced those tables, which is what such a store
        really carries. Keying the check on the *current* version instead makes every later
        migration reclassify this store as merely outdated and then attempt an upgrade that
        cannot work.
        """
        conn.execute(
            "CREATE TABLE IF NOT EXISTS signals_schema_meta "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "INSERT OR REPLACE INTO signals_schema_meta(key, value) "
            "VALUES ('schema_version', ?)", (str(SNAPSHOT_TABLES_VERSION),))
        conn.execute("CREATE TABLE security_refresh_runs (run_id TEXT PRIMARY KEY)")
        conn.commit()

        with pytest.raises(SignalsSchemaUnsupportedError) as excinfo:
            apply_signals_migrations(conn)
        message = str(excinfo.value)
        # The repair must stay scoped to the SIGNAL tables: the co-located file also
        # holds the authored STPA/CAST/GRC model, which is not regenerable.
        assert "security_refresh_runs" in message
        assert "Do NOT delete the assurance database file" in message

    def test_a_store_carrying_the_old_vex_column_is_migrated_in_place(self, conn: Any) -> None:
        """The upgrade path for a store created before the column was named after its
        vocabulary. The rename must happen without touching the rows it holds."""
        _bring_to_version(conn, SNAPSHOT_TABLES_VERSION)
        conn.execute(
            "INSERT INTO vex_assessments (assessment_id, anchor_entity_id, "
            "canonical_component_id, canonical_vulnerability_id, revision, disposition, "
            "justification, author, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("VEX@1", "APP@1", "pkg:x@1", "VID@1", 1, "not_affected", "vendored copy unused",
             "analyst", "2026-07-26T00:00:00Z"),
        )
        conn.commit()

        assert apply_signals_migrations(conn) == SIGNALS_SCHEMA_VERSION

        columns = {row["name"] for row in conn.execute(
            "PRAGMA table_info(vex_assessments)").fetchall()}
        assert "vex_status" in columns
        assert "disposition" not in columns
        row = conn.execute("SELECT * FROM vex_assessments").fetchone()
        assert row["vex_status"] == "not_affected", "the assessment must survive the rename"
        assert row["justification"] == "vendored copy unused"

    def test_current_store_is_not_mistaken_for_a_pre_rename_one(self, conn: Any) -> None:
        """The detector keys on table names, so a migrated store carrying a leftover
        pre-rename table alongside the current one must still open."""
        apply_signals_migrations(conn)
        conn.execute("CREATE TABLE security_refresh_runs (run_id TEXT PRIMARY KEY)")
        conn.commit()

        assert apply_signals_migrations(conn) == SIGNALS_SCHEMA_VERSION

    def test_several_connections_may_migrate_the_same_store_at_once(self, tmp_path: Path) -> None:
        """The threadpool opens a connection per thread and each migrates on open.

        A migration's statements are not all individually idempotent — a column rename fails on
        an already-renamed schema — so the loser of the race must recognise that the migration
        is done rather than re-run it.

        The barrier is a *best-effort* rendezvous, not part of the assertion. It exists to make
        the four migrations overlap, which is what gives the race a chance to happen at all — but
        a rendezvous that fails to line up says nothing about migrations. `Barrier.wait` breaks
        the barrier for *every* participant as soon as one is starved past the timeout, so
        treating that as a failure turned one starved thread on a saturated box into a failed
        test about concurrency. Under load the threads may now overlap less and prove less; they
        never report a defect that is not there.

        Timeouts are deliberately generous for the same reason: the busy timeout bounds lock
        waiting, which is not the thing under test and is the first thing a parallel suite starves.
        """
        import threading

        patience_seconds = 300.0  # full-suite -n 8 load has starved 120s on this box
        db = tmp_path / "signals.db"
        errors: list[str] = []
        barrier = threading.Barrier(4)

        def _migrate() -> None:
            conn = sqlite3.connect(str(db), timeout=patience_seconds)
            conn.row_factory = _dict_row  # type: ignore[assignment]
            conn.executescript(SIGNALS_PRAGMAS_SQL)
            try:
                try:
                    barrier.wait(timeout=patience_seconds)
                except threading.BrokenBarrierError:
                    pass  # starved rendezvous — migrate anyway, that is what is under test
                apply_signals_migrations(conn)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                conn.close()

        threads = [threading.Thread(target=_migrate) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=patience_seconds)

        # `join(timeout=…)` returns silently on a straggler, and the assertions below would then
        # describe a store still being migrated. A thread still running after this long is a hang,
        # and must be reported as one rather than as a schema mismatch.
        still_running = [t.name for t in threads if t.is_alive()]
        assert not still_running, f"migration threads did not finish within {patience_seconds}s: {still_running}"

        assert not errors, f"concurrent migration errors: {errors[:3]}"
        conn = sqlite3.connect(str(db))
        conn.row_factory = _dict_row  # type: ignore[assignment]
        assert signals_schema_version(conn) == SIGNALS_SCHEMA_VERSION
        columns = {row["name"] for row in conn.execute(
            "PRAGMA table_info(vex_assessments)").fetchall()}
        assert "vex_status" in columns and "disposition" not in columns
        conn.close()

    def test_all_snapshot_tables_exist(self, conn: Any) -> None:
        apply_signals_migrations(conn)
        tables = {
            row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "security_signal_snapshots", "snapshot_components", "canonical_vulnerabilities",
            "vulnerability_aliases", "snapshot_vulnerability_findings", "vex_assessments",
            "signals_schema_meta",
        } <= tables


class TestConstraints:
    def _insert_run(self, conn: Any, snapshot_id: str, anchor: str, request_id: str,
                    status: str) -> None:
        conn.execute(
            "INSERT INTO security_signal_snapshots "
            "(snapshot_id, anchor_entity_id, request_id, request_payload_digest, status, started_at) "
            "VALUES (?,?,?,?,?,?)",
            (snapshot_id, anchor, request_id, "d1", status, "2026-07-20T00:00:00Z"),
        )

    def test_one_active_run_per_anchor_is_a_db_constraint(self, conn: Any) -> None:
        apply_signals_migrations(conn)
        self._insert_run(conn, "SNAP@1", "APP@1", "req-1", "active")
        with pytest.raises(Exception, match="(?i)unique"):
            self._insert_run(conn, "SNAP@2", "APP@1", "req-2", "active")
        # A second active snapshot on a DIFFERENT anchor is fine; superseded on the
        # same anchor is fine.
        self._insert_run(conn, "SNAP@3", "APP@2", "req-3", "active")
        self._insert_run(conn, "SNAP@4", "APP@1", "req-4", "superseded")

    def test_replay_key_is_unique_per_anchor(self, conn: Any) -> None:
        apply_signals_migrations(conn)
        self._insert_run(conn, "SNAP@1", "APP@1", "req-1", "staging")
        with pytest.raises(Exception, match="(?i)unique"):
            self._insert_run(conn, "SNAP@2", "APP@1", "req-1", "staging")
        # Same request_id under another anchor is a different key.
        self._insert_run(conn, "SNAP@3", "APP@2", "req-1", "staging")

    def test_findings_are_unique_per_run_component_vulnerability(self, conn: Any) -> None:
        apply_signals_migrations(conn)
        self._insert_run(conn, "SNAP@1", "APP@1", "req-1", "staging")
        conn.execute(
            "INSERT INTO snapshot_components (component_id, snapshot_id, name) VALUES ('C1','SNAP@1','requests')"
        )
        conn.execute(
            "INSERT INTO snapshot_vulnerability_findings "
            "(finding_id, snapshot_id, component_id, canonical_vulnerability_id) "
            "VALUES ('F1','SNAP@1','C1','VID@a')"
        )
        with pytest.raises(Exception, match="(?i)unique"):
            conn.execute(
                "INSERT INTO snapshot_vulnerability_findings "
                "(finding_id, snapshot_id, component_id, canonical_vulnerability_id) "
                "VALUES ('F2','SNAP@1','C1','VID@a')"
            )
