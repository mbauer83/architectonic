"""Snapshot deletion: what it removes, what it deliberately does NOT remove, and
that both transports gate and report identically.

Deletion is the only destructive signal mutation, so its blast radius is asserted
explicitly: shared vulnerability identities and anchor-scoped VEX assessments must
survive, or deleting one scan would quietly rewrite another anchor's history.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.assurance._snapshot_store import SQLCipherSnapshotStore

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def store(tmp_path: Path):  # type: ignore[no-untyped-def]
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "deletion.db"
    init_store(db_path)
    sql_store = SQLCipherAssuranceStore(db_path)
    sql_store.unlock()
    yield SQLCipherSnapshotStore(sql_store._thread_conn_or_none)  # noqa: SLF001
    sql_store.lock()


def _activated(store: Any, snapshot_id: str, *, anchor: str, request_id: str) -> None:
    store.create_staging_snapshot(
        snapshot_id=snapshot_id, anchor_entity_id=anchor, request_id=request_id,
        request_payload_digest=f"d-{request_id}",
    )
    store.populate_snapshot(
        snapshot_id,
        components=[{"component_id": "C1", "name": "urllib3", "purl": "pkg:pypi/urllib3@1"}],
        findings=[{"component_id": "C1", "external_ids": ["CVE-2026-1"]}],
    )
    store.complete_snapshot(snapshot_id)
    store.activate_snapshot(snapshot_id)


class TestDeleteOneSnapshot:
    def test_removes_the_snapshot_with_its_components_and_findings(self, store: Any) -> None:
        _activated(store, "SNAP@1", anchor="APP@1.aaa", request_id="r1")

        removed = store.delete_snapshot("SNAP@1")

        assert removed is not None
        assert removed["component_count"] == 1
        assert removed["finding_count"] == 1
        assert store.get_snapshot("SNAP@1") is None
        assert store.list_snapshot_components("SNAP@1") == []
        assert store.list_snapshot_findings("SNAP@1") == []

    def test_deleting_the_active_snapshot_leaves_the_anchor_with_none(
        self, store: Any,
    ) -> None:
        """Refusing would make an anchor whose ONLY snapshot is active
        undeletable — the junk-anchor case deletion exists for."""
        _activated(store, "SNAP@1", anchor="APP@1.aaa", request_id="r1")

        removed = store.delete_snapshot("SNAP@1")

        assert removed["was_active"] is True
        assert store.get_active_snapshot("APP@1.aaa") is None

    def test_no_earlier_snapshot_is_promoted_back_to_active(self, store: Any) -> None:
        """superseded -> active is not an allowed transition, and resurrecting a
        stale scan as current truth would be worse than reporting none."""
        _activated(store, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        _activated(store, "SNAP@2", anchor="APP@1.aaa", request_id="r2")  # supersedes SNAP@1

        store.delete_snapshot("SNAP@2")

        assert store.get_active_snapshot("APP@1.aaa") is None
        assert store.get_snapshot("SNAP@1")["status"] == "superseded"

    def test_an_unknown_id_is_reported_not_raised(self, store: Any) -> None:
        assert store.delete_snapshot("SNAP@nope") is None

    def test_another_anchors_snapshot_is_untouched(self, store: Any) -> None:
        _activated(store, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        _activated(store, "SNAP@2", anchor="APP@2.bbb", request_id="r2")

        store.delete_snapshot("SNAP@1")

        assert store.get_active_snapshot("APP@2.bbb")["snapshot_id"] == "SNAP@2"
        assert len(store.list_snapshot_findings("SNAP@2")) == 1

    def test_resolves_either_anchor_id_form_via_the_stable_key(self, store: Any) -> None:
        _activated(store, "SNAP@1", anchor="APP@1777293133.OYEmP1", request_id="r1")

        removed = store.delete_anchor_snapshots("APP@1777293133.OYEmP1.architecture-backend")

        assert [entry["snapshot_id"] for entry in removed] == ["SNAP@1"]


class TestBlastRadius:
    """What deletion must NOT touch."""

    def _conn(self, store: Any) -> Any:
        return store.connection.open()

    def test_shared_vulnerability_identities_and_aliases_survive(self, store: Any) -> None:
        """Other snapshots resolve findings through these rows; cascading them away
        would corrupt every anchor that shares a vulnerability."""
        _activated(store, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        conn = self._conn(store)
        before_canonical = conn.execute(
            "SELECT COUNT(*) AS n FROM canonical_vulnerabilities").fetchone()["n"]
        before_aliases = conn.execute(
            "SELECT COUNT(*) AS n FROM vulnerability_aliases").fetchone()["n"]
        assert before_canonical > 0 and before_aliases > 0

        store.delete_snapshot("SNAP@1")

        conn = self._conn(store)
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM canonical_vulnerabilities").fetchone()["n"] == before_canonical
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM vulnerability_aliases").fetchone()["n"] == before_aliases

    def test_vex_assessments_survive(self, store: Any) -> None:
        """A VEX assessment is anchor-and-vulnerability scoped: it outlives the scan
        that surfaced the finding, and re-ingesting must not lose the analyst's call."""
        _activated(store, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        conn = self._conn(store)
        conn.execute(
            "INSERT INTO vex_assessments (assessment_id, anchor_entity_id, "
            "canonical_component_id, canonical_vulnerability_id, revision, vex_status, "
            "author, created_at) VALUES ('VEX@1','APP@1.aaa','C1','VID@x',1,"
            "'not_affected','analyst','2026-07-21T00:00:00Z')")
        conn.commit()

        store.delete_snapshot("SNAP@1")

        conn = self._conn(store)
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM vex_assessments").fetchone()["n"] == 1

    def test_the_deletion_is_audited(self, store: Any) -> None:
        _activated(store, "SNAP@1", anchor="APP@1.aaa", request_id="r1")

        store.delete_snapshot("SNAP@1")

        conn = self._conn(store)
        rows = conn.execute("SELECT operation, payload_json FROM audit_log").fetchall()
        deletions = [r for r in rows if r["operation"] == "SIGNAL_SNAPSHOT_DELETED"]
        assert len(deletions) == 1
        # The audit row must carry what was destroyed, not merely that something was.
        assert "SNAP@1" in deletions[0]["payload_json"]


class TestDeleteAnchorSnapshots:
    def test_removes_every_snapshot_for_the_anchor_only(self, store: Any) -> None:
        _activated(store, "SNAP@1", anchor="APP@1.aaa", request_id="r1")
        _activated(store, "SNAP@2", anchor="APP@1.aaa", request_id="r2")
        _activated(store, "SNAP@3", anchor="APP@2.bbb", request_id="r3")

        removed = store.delete_anchor_snapshots("APP@1.aaa")

        assert {entry["snapshot_id"] for entry in removed} == {"SNAP@1", "SNAP@2"}
        assert store.list_snapshots(anchor_entity_id="APP@1.aaa") == []
        assert len(store.list_snapshots(anchor_entity_id="APP@2.bbb")) == 1

    def test_an_anchor_with_no_snapshots_removes_nothing(self, store: Any) -> None:
        assert store.delete_anchor_snapshots("APP@absent.zzz") == []
