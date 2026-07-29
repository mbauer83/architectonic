"""The registered operational migration reconciling pre-handbook assurance
vocabulary in a real seeded SQLCipher store: deterministic rewrites only,
undecidable vocabulary reported as manual findings, rerun-safe."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.deployment_upgrade.orchestrate import apply_targets, evaluate_targets
from src.application.deployment_upgrade.ports import build_operational_registry
from src.domain.repository.operational_upgrade import UpgradeTarget
from src.infrastructure.deployment.database_targets import (
    DatabaseTargetHandle,
    sqlcipher_connection_factory,
)

_KEY = "test-key"


def _seed_store(path: Path) -> None:
    sqlcipher3 = pytest.importorskip("sqlcipher3")
    conn = sqlcipher3.connect(str(path))
    conn.execute(f"PRAGMA key = '{_KEY}'")
    conn.execute(
        "CREATE TABLE assurance_nodes (node_id TEXT PRIMARY KEY, node_type TEXT NOT NULL, name TEXT)"
    )
    conn.execute(
        "CREATE TABLE assurance_edges (edge_id TEXT PRIMARY KEY, source_id TEXT, target_id TEXT, conn_type TEXT)"
    )
    conn.execute(
        "CREATE TABLE arch_refs (assurance_node_id TEXT, arch_artifact_id TEXT, ref_type TEXT, resolved_at TEXT)"
    )
    nodes = [
        ("UCA@1", "unsafe-control-action", "UCA one"),
        ("UCA@2", "unsafe-control-action", "UCA two"),
        ("HAZ@1", "hazard", "Hazard"),
        ("ACN@1", "assurance-constraint", "Constraint"),
        ("RSK@1", "risk", "Risk"),
        ("CSN@1", "control-structure-node", "Controller"),
    ]
    conn.executemany("INSERT INTO assurance_nodes VALUES (?,?,?)", nodes)
    edges = [
        # violates duplicated by an existing leads-to → deleted
        ("E1", "UCA@1", "HAZ@1", "violates"),
        ("E2", "UCA@1", "HAZ@1", "leads-to"),
        # violates without a parallel leads-to → retyped
        ("E3", "UCA@2", "HAZ@1", "violates"),
        # accountable-to flips per source node type
        ("E4", "ACN@1", "CSN@1", "accountable-to"),
        ("E5", "RSK@1", "CSN@1", "accountable-to"),
        # undecidable vocabulary → manual finding, untouched
        ("E6", "ACN@1", "ACN@1", "satisfied-by"),
    ]
    conn.executemany("INSERT INTO assurance_edges VALUES (?,?,?,?)", edges)
    conn.executemany(
        "INSERT INTO arch_refs VALUES (?,?,?,NULL)",
        [
            ("ACN@1", "REQ@1.abc.some-requirement", "refines"),
            ("ACN@1", "APP@1.abc.some-component", "evidenced-by"),
            ("CSN@1", "APP@1.abc.some-component", "binds-to"),
        ],
    )
    conn.commit()
    conn.close()


def _handle(path: Path) -> DatabaseTargetHandle:
    return DatabaseTargetHandle(
        target=UpgradeTarget(
            kind="assurance_sqlcipher",
            stable_id=f"assurance_sqlcipher:{path}",
            display_location=str(path),
            current_version=0,
            credential_requirement="sqlcipher_key",
        ),
        connect=sqlcipher_connection_factory(path, _KEY),
        inspectable=True,
    )


def _rows(path: Path, sql: str) -> list[tuple]:
    conn = sqlcipher_connection_factory(path, _KEY)()
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


class TestDetect:
    def test_reports_each_legacy_pattern(self, tmp_path: Path) -> None:
        db = tmp_path / "store.db"
        _seed_store(db)
        reports = evaluate_targets((_handle(db),), build_operational_registry())
        finding_ids = {r.finding.finding_id for r in reports[0].results}
        assert finding_ids == {
            "violates-edges",
            "accountable-to-edges",
            "undecidable-legacy-edges",
            "legacy-reference-types",
            "signals-schema-outdated",  # the signals step also covers this target kind
        }
        manual = [r for r in reports[0].results if not r.finding.auto_migratable]
        assert len(manual) == 1

    def test_reconciled_store_is_current(self, tmp_path: Path) -> None:
        db = tmp_path / "store.db"
        _seed_store(db)
        apply_targets((_handle(db),), build_operational_registry())
        reports = evaluate_targets((_handle(db),), build_operational_registry())
        finding_ids = {r.finding.finding_id for r in reports[0].results}
        assert finding_ids == {"undecidable-legacy-edges"}  # manual work remains visible


class TestApply:
    def test_deterministic_rewrites(self, tmp_path: Path) -> None:
        db = tmp_path / "store.db"
        _seed_store(db)
        reports, failed = apply_targets((_handle(db),), build_operational_registry())
        assert failed is None
        assert reports[0].committed

        # Duplicate violates deleted; lone violates retyped.
        assert _rows(db, "SELECT count(*) FROM assurance_edges WHERE conn_type='violates'")[0][0] == 0
        leads = _rows(
            db, "SELECT source_id, target_id FROM assurance_edges WHERE conn_type='leads-to' ORDER BY source_id"
        )
        assert leads == [("UCA@1", "HAZ@1"), ("UCA@2", "HAZ@1")]

        # accountable-to flipped per source type.
        assert _rows(
            db, "SELECT source_id, target_id FROM assurance_edges WHERE conn_type='responsible-for'"
        ) == [("CSN@1", "ACN@1")]
        assert _rows(
            db, "SELECT source_id, target_id FROM assurance_edges WHERE conn_type='accountable-for'"
        ) == [("CSN@1", "RSK@1")]
        assert _rows(db, "SELECT count(*) FROM assurance_edges WHERE conn_type='accountable-to'")[0][0] == 0

        # Undecidable vocabulary untouched.
        assert _rows(db, "SELECT count(*) FROM assurance_edges WHERE conn_type='satisfied-by'")[0][0] == 1

        # Reference types renamed; binds-to untouched.
        refs = dict(_rows(db, "SELECT ref_type, count(*) FROM arch_refs GROUP BY ref_type"))
        assert refs == {"binds-to": 1, "evidenced-by-artifact": 1, "refines-requirement": 1}

    def test_rerun_is_a_no_op(self, tmp_path: Path) -> None:
        db = tmp_path / "store.db"
        _seed_store(db)
        apply_targets((_handle(db),), build_operational_registry())
        before = _rows(db, "SELECT * FROM assurance_edges ORDER BY edge_id")
        apply_targets((_handle(db),), build_operational_registry())
        assert _rows(db, "SELECT * FROM assurance_edges ORDER BY edge_id") == before
