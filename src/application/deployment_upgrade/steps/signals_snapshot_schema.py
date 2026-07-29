"""Operational migration: bring a security-signals database to the signal-snapshot
schema (versioned ``signals_schema_meta`` + the snapshot aggregate tables).

The signal-snapshot aggregate is the sole signals model; metrics read only the
active snapshot. The public SQLite backend is deprecated for metrics but its schema
is kept current for queryability.

Two conditions are detected. An OUTDATED store (below the current version) migrates
automatically. A PRE-RENAME store — stamped at the current version but still carrying
the old ``security_refresh_runs`` tables — cannot be migrated: the version-2 DDL was
renamed in place during pre-alpha rather than versioned forward, so there is no
upgrade path and the store must be recreated. That case is reported as a blocking,
non-auto-migratable finding rather than left to fail later as a missing table."""

from __future__ import annotations

from src.application.deployment_upgrade.ports import (
    OperationalTargetUnitOfWork,
    OperationalTargetView,
)
from src.domain.assurance.signals_schema import (
    SIGNALS_MIGRATIONS,
    SIGNALS_SCHEMA_VERSION,
    SNAPSHOT_TABLES_VERSION,
    signals_migration_statements,
)
from src.domain.repository.operational_upgrade import TargetKind
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding


def _table_exists(view: OperationalTargetView, table: str) -> bool:
    value = view.query_scalar(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return bool(int(value)) if isinstance(value, (int, float, str)) else False


def _current_version(view: OperationalTargetView) -> int:
    if not _table_exists(view, "signals_schema_meta"):
        return 1
    value = view.query_scalar(
        "SELECT value FROM signals_schema_meta WHERE key='schema_version'"
    )
    return int(value) if isinstance(value, (int, float, str)) else 1


def _is_pre_rename(view: OperationalTargetView, current: int) -> bool:
    """A store stamped as having the snapshot tables whose snapshot table is absent while
    the pre-rename run table is present. Version alone cannot distinguish it — both
    schemas are stamped 2 — so the table names are the only available evidence.

    Compared against the version that introduced those tables rather than the current one, so
    that a later migration does not reclassify this store as merely outdated and then try to
    migrate a schema with no upgrade path.
    """
    return (
        current >= SNAPSHOT_TABLES_VERSION
        and not _table_exists(view, "security_signal_snapshots")
        and _table_exists(view, "security_refresh_runs")
    )


class _SignalsSnapshotSchemaStep:
    id = "signals-0002-signal-snapshot-schema"
    version = 1
    kind: TargetKind = "assurance_sqlcipher"
    description = "Versioned signal-snapshot schema for security signals"

    def detect(self, view: OperationalTargetView) -> list[UpgradeFinding]:
        findings: list[UpgradeFinding] = []
        location = view.target.display_location
        current = _current_version(view)
        if _is_pre_rename(view, current):
            findings.append(UpgradeFinding(
                step_id=self.id,
                finding_id="signals-schema-pre-rename",
                location=location,
                description=(
                    f"security-signals schema is stamped version {current} but still carries "
                    "the pre-rename tables (security_refresh_runs); the version-2 DDL was "
                    "renamed in place during pre-alpha, so this store has no upgrade path"
                ),
                severity="error",
                auto_migratable=False,
                manual_instructions=(
                    "No upgrade path exists from the pre-rename version-2 tables to the "
                    "signal-snapshot tables. Drop the pre-rename SIGNAL tables "
                    "(run_vulnerability_findings, run_components, security_refresh_runs), "
                    "reset signals_schema_meta.schema_version to 1 so the current DDL is "
                    "reapplied, then re-run ingest — the dropped contents are regenerated "
                    "from the SBOM and advisory sources. Resetting the stamp is required: "
                    "dropping the tables alone leaves the schema stamped current with no "
                    "signal tables, which fails the same way. Do NOT delete the assurance "
                    "database file: in the co-located backend it also holds the authored "
                    "STPA/CAST/GRC model, which is not regenerable."
                ),
                blocks_commit=True,
            ))
            return findings
        if current < SIGNALS_SCHEMA_VERSION:
            findings.append(UpgradeFinding(
                step_id=self.id,
                finding_id="signals-schema-outdated",
                location=location,
                description=(
                    f"security-signals schema is at version {current}; "
                    f"version {SIGNALS_SCHEMA_VERSION} is current"
                ),
                severity="warning",
                auto_migratable=True,
                rewrite_summary="apply the ordered signals migrations (signal-snapshot tables + version stamp)",
            ))
        return findings

    def apply(
        self,
        view: OperationalTargetView,
        uow: OperationalTargetUnitOfWork,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        schema_finding = next(
            (f for f in findings if f.finding_id == "signals-schema-outdated"), None,
        )
        if schema_finding is None:
            return []
        uow.execute_sql(
            "CREATE TABLE IF NOT EXISTS signals_schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        current = _current_version(view)
        for version, ddl in SIGNALS_MIGRATIONS:
            if version <= current:
                continue
            for statement in signals_migration_statements(ddl):
                uow.execute_sql(statement)
            uow.execute_sql(
                "INSERT OR REPLACE INTO signals_schema_meta(key, value) VALUES ('schema_version', ?)",
                (str(version),),
            )
        return [AppliedFinding(
            finding=schema_finding,
            outcome="applied",
            detail=f"migrated signals schema to version {SIGNALS_SCHEMA_VERSION}",
        )]



class SignalsSnapshotSchemaStep(_SignalsSnapshotSchemaStep):
    """Co-located SQLCipher signals (the metrics-capable backend)."""

    id = "signals-0002-signal-snapshot-schema"
    kind: TargetKind = "assurance_sqlcipher"


class PublicSqliteSignalsSchemaStep(_SignalsSnapshotSchemaStep):
    """Public SQLite signals file — schema kept current for queryability even
    though the backend is deprecated for metrics."""

    id = "signals-0002-signal-snapshot-schema-public"
    kind: TargetKind = "signals_sqlite"
