"""Signals-schema upgrade step: detects an outdated (pre-signal-snapshot) schema and
applies the versioned migration through the operational unit of work,
idempotently — on the SQLCipher target kind and the public SQLite kind."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.application.deployment_upgrade.orchestrate import apply_targets, evaluate_targets
from src.application.deployment_upgrade.ports import OperationalStepRegistry
from src.application.deployment_upgrade.steps.signals_snapshot_schema import (
    PublicSqliteSignalsSchemaStep,
    SignalsSnapshotSchemaStep,
)
from src.domain.assurance.signals_schema import SIGNALS_SCHEMA_VERSION
from src.domain.repository.operational_upgrade import UpgradeTarget
from src.infrastructure.deployment.database_targets import DatabaseTargetHandle


def _seed_public_signals(path: Path) -> None:
    """A pre-signal-snapshot signals file: no signals_schema_meta, so it reads as the
    baseline version and the step detects it as outdated."""
    conn = sqlite3.connect(str(path))
    conn.commit()
    conn.close()


def _handle(path: Path) -> DatabaseTargetHandle:
    return DatabaseTargetHandle(
        target=UpgradeTarget(
            kind="signals_sqlite",
            stable_id=f"signals_sqlite:{path}",
            display_location=str(path),
            current_version=0,
            credential_requirement="none",
        ),
        connect=lambda: sqlite3.connect(str(path)),
        inspectable=True,
    )


def _registry() -> OperationalStepRegistry:
    registry = OperationalStepRegistry()
    registry.register(SignalsSnapshotSchemaStep())
    registry.register(PublicSqliteSignalsSchemaStep())
    return registry


def _seed_pre_rename_signals(path: Path) -> None:
    """A store stamped as having the snapshot tables but carrying the pre-rename ones.
    Version 2's DDL was renamed in place during pre-alpha, so version alone cannot
    distinguish this store from one that really has the snapshot tables — only the table
    names can."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE signals_schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute(
        "INSERT INTO signals_schema_meta(key, value) VALUES ('schema_version', '2')")
    conn.execute("CREATE TABLE security_refresh_runs (run_id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()


class TestDetect:
    def test_outdated_schema_is_an_auto_migratable_finding(self, tmp_path: Path) -> None:
        db = tmp_path / "signals.db"
        _seed_public_signals(db)
        reports = evaluate_targets((_handle(db),), _registry())
        by_id = {r.finding.finding_id: r.finding for r in reports[0].results}
        assert set(by_id) == {"signals-schema-outdated"}
        assert by_id["signals-schema-outdated"].auto_migratable is True

    def test_pre_rename_store_blocks_instead_of_reading_as_current(
        self, tmp_path: Path,
    ) -> None:
        """Regression: a store stamped version 2 under the old table names would
        otherwise report clean and then fail at query time on a missing table.
        It has no upgrade path, so it must surface as a blocking manual finding.

        It must keep doing so once later versions exist, when such a store is no longer stamped
        at the current version — otherwise it reads as merely outdated and the auto-migration is
        pointed at a schema that cannot be migrated."""
        db = tmp_path / "signals.db"
        _seed_pre_rename_signals(db)
        reports = evaluate_targets((_handle(db),), _registry())
        by_id = {r.finding.finding_id: r.finding for r in reports[0].results}

        assert set(by_id) == {"signals-schema-pre-rename"}
        finding = by_id["signals-schema-pre-rename"]
        assert finding.severity == "error"
        assert finding.auto_migratable is False
        assert finding.blocks_commit is True
        instructions = (finding.manual_instructions or "").lower()
        # Signal-scoped repair only: the co-located file also holds the authored
        # STPA/CAST/GRC model, so "delete the database" would be destructive advice.
        assert "security_refresh_runs" in instructions
        assert "do not delete the assurance database file" in instructions


class TestApply:
    def test_migration_applies_and_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "signals.db"
        _seed_public_signals(db)
        reports, failed = apply_targets((_handle(db),), _registry())
        assert failed is None
        assert reports[0].committed

        conn = sqlite3.connect(str(db))
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "security_signal_snapshots" in tables and "vex_assessments" in tables
        version = conn.execute(
            "SELECT value FROM signals_schema_meta WHERE key='schema_version'").fetchone()[0]
        assert version == str(SIGNALS_SCHEMA_VERSION), "the stamp must reach the current version"
        vex_columns = {row[1] for row in conn.execute(
            "PRAGMA table_info(vex_assessments)").fetchall()}
        assert "vex_status" in vex_columns and "disposition" not in vex_columns
        conn.close()

        # Idempotent: once current, re-evaluation reports nothing.
        reports = evaluate_targets((_handle(db),), _registry())
        assert {r.finding.finding_id for r in reports[0].results} == set()
