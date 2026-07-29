"""Signal-snapshot store integration (real SQLCipher): lifecycle transitions with
audit in the same transaction, atomic activation (crash leaves the previous
snapshot the sole basis), the one-active-per-anchor DB constraint through the
adapter, idempotent replay wiring, stale-staging recovery, and alias-merge
repointing across findings and VEX rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import src.infrastructure.assurance._snapshot_lifecycle as lifecycle_module
from src.domain.assurance.security_signal_snapshot import ReplayStoredSuccess, StoredSnapshotKey, replay_decision
from src.infrastructure.assurance._snapshot_store import (
    SnapshotTransitionError,
    SQLCipherSnapshotStore,
)

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")


@pytest.fixture()
def store(tmp_path: Path):
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "snapshots.db"
    init_store(db_path)
    sql_store = SQLCipherAssuranceStore(db_path)
    sql_store.unlock()
    yield SQLCipherSnapshotStore(sql_store._thread_conn_or_none)  # noqa: SLF001
    sql_store.lock()


def _staging(store: SQLCipherSnapshotStore, snapshot_id: str = "SNAP@1",
             anchor: str = "APP@1", request_id: str = "req-1", digest: str = "d1") -> None:
    store.create_staging_snapshot(
        snapshot_id=snapshot_id, anchor_entity_id=anchor, request_id=request_id,
        request_payload_digest=digest,
    )


class TestLifecycle:
    def test_full_lifecycle_with_timestamps_and_audit(self, store: Any) -> None:
        _staging(store)
        store.populate_snapshot("SNAP@1", components=[
            {"component_id": "C1", "name": "requests", "purl": "pkg:pypi/requests@2.31.0",
             "version": "2.31.0", "directness": "direct"},
        ], findings=[
            {"component_id": "C1", "external_ids": ["CVE-2024-1"], "severity_band": "high",
             "cvss_score": 8.1},
        ])
        store.complete_snapshot("SNAP@1")
        result = store.activate_snapshot("SNAP@1")
        assert result == {"snapshot_id": "SNAP@1", "activated": True, "superseded_snapshot_id": None}
        snapshot = store.get_snapshot("SNAP@1")
        assert snapshot["status"] == "active"
        assert snapshot["completed_at"] and snapshot["activated_at"]
        assert snapshot["superseded_at"] is None

    def test_activation_requires_complete(self, store: Any) -> None:
        _staging(store)
        with pytest.raises(SnapshotTransitionError):
            store.activate_snapshot("SNAP@1")

    def test_reactivating_the_active_run_is_a_noop_success(self, store: Any) -> None:
        _staging(store)
        store.complete_snapshot("SNAP@1")
        store.activate_snapshot("SNAP@1")
        assert store.activate_snapshot("SNAP@1") == {
            "snapshot_id": "SNAP@1", "activated": False, "already_active": True,
        }

    def test_failed_is_terminal(self, store: Any) -> None:
        _staging(store)
        store.fail_snapshot("SNAP@1", reason="acquisition failed")
        with pytest.raises(SnapshotTransitionError):
            store.complete_snapshot("SNAP@1")
        with pytest.raises(SnapshotTransitionError):
            store.populate_snapshot("SNAP@1", components=[], findings=[])


class TestActivationAtomicity:
    def test_new_activation_supersedes_the_previous_in_one_step(self, store: Any) -> None:
        _staging(store, "SNAP@1", request_id="req-1")
        store.complete_snapshot("SNAP@1")
        store.activate_snapshot("SNAP@1")
        _staging(store, "SNAP@2", request_id="req-2")
        store.complete_snapshot("SNAP@2")
        result = store.activate_snapshot("SNAP@2")
        assert result["superseded_snapshot_id"] == "SNAP@1"
        assert store.get_snapshot("SNAP@1")["status"] == "superseded"
        assert store.get_snapshot("SNAP@1")["superseded_at"]
        assert store.get_active_snapshot("APP@1")["snapshot_id"] == "SNAP@2"

    def test_crash_inside_activation_leaves_the_previous_run_active(
        self, store: Any, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _staging(store, "SNAP@1", request_id="req-1")
        store.complete_snapshot("SNAP@1")
        store.activate_snapshot("SNAP@1")
        _staging(store, "SNAP@2", request_id="req-2")
        store.complete_snapshot("SNAP@2")

        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("crash before commit")

        monkeypatch.setattr(lifecycle_module, "append_audit_row", _boom)
        with pytest.raises(RuntimeError, match="crash before commit"):
            store.activate_snapshot("SNAP@2")
        monkeypatch.undo()
        # The whole transaction rolled back: SNAP@1 still sole active basis.
        assert store.get_active_snapshot("APP@1")["snapshot_id"] == "SNAP@1"
        assert store.get_snapshot("SNAP@2")["status"] == "complete"

    def test_crash_during_population_leaves_no_partial_rows(
        self, store: Any, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _staging(store)

        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("crash before commit")

        monkeypatch.setattr(lifecycle_module, "append_audit_row", _boom)
        with pytest.raises(RuntimeError):
            store.populate_snapshot("SNAP@1", components=[
                {"component_id": "C1", "name": "requests"},
            ], findings=[])
        monkeypatch.undo()
        conn = store.connection.open()
        assert conn.execute("SELECT COUNT(*) AS n FROM snapshot_components").fetchone()["n"] == 0


class TestReplayWiring:
    def test_stored_run_feeds_the_domain_replay_table(self, store: Any) -> None:
        _staging(store, digest="d1")
        store.complete_snapshot("SNAP@1")
        store.activate_snapshot("SNAP@1")
        row = store.find_snapshot_by_request("APP@1", "req-1")
        key = StoredSnapshotKey(
            snapshot_id=row["snapshot_id"], status=row["status"],
            request_payload_digest=row["request_payload_digest"],
        )
        assert replay_decision(key, "d1") == ReplayStoredSuccess(snapshot_id="SNAP@1")

    def test_duplicate_key_is_rejected_by_the_db(self, store: Any) -> None:
        _staging(store, "SNAP@1", request_id="req-1")
        with pytest.raises(Exception, match="(?i)unique"):
            _staging(store, "SNAP@2", request_id="req-1")


class TestStaleStaging:
    def test_stale_staging_runs_are_failed_never_activated(self, store: Any) -> None:
        _staging(store, "SNAP@1", request_id="req-1")
        failed = store.fail_stale_staging(started_before_iso="9999-01-01T00:00:00Z")
        assert failed == ["SNAP@1"]
        assert store.get_snapshot("SNAP@1")["status"] == "failed"
        assert store.get_active_snapshot("APP@1") is None

    def test_fresh_staging_runs_are_untouched(self, store: Any) -> None:
        _staging(store, "SNAP@1", request_id="req-1")
        assert store.fail_stale_staging(started_before_iso="2000-01-01T00:00:00Z") == []
        assert store.get_snapshot("SNAP@1")["status"] == "staging"


class TestAliasMerge:
    def test_linking_two_groups_repoints_findings_transactionally(self, store: Any) -> None:
        _staging(store, "SNAP@1", request_id="req-1")
        store.populate_snapshot("SNAP@1", components=[
            {"component_id": "C1", "name": "a"},
            {"component_id": "C2", "name": "b"},
        ], findings=[
            {"component_id": "C1", "external_ids": ["CVE-2024-1"]},
            {"component_id": "C2", "external_ids": ["GHSA-x"]},
        ])
        # A later record reveals the two ids are the same vulnerability.
        population = store.populate_snapshot("SNAP@1", components=[], findings=[
            {"component_id": "C1", "external_ids": ["CVE-2024-1", "GHSA-x"]},
        ])
        canonical = next(iter(population.canonical_by_external_id.values()))
        conn = store.connection.open()
        distinct = conn.execute(
            "SELECT COUNT(DISTINCT canonical_vulnerability_id) AS n FROM snapshot_vulnerability_findings"
        ).fetchone()["n"]
        assert distinct == 1
        merged = conn.execute(
            "SELECT COUNT(*) AS n FROM canonical_vulnerabilities WHERE merged_into=?",
            (canonical,),
        ).fetchone()["n"]
        assert merged == 1  # history preserved, not deleted


class TestAnchorIdentity:
    """Snapshots are keyed by the STABLE (slug-free) anchor id.

    Regression: the GUI navigates by the full ``PREFIX@epoch.random.slug`` id
    while scripts and MCP callers use the short one. The store matches anchors by
    exact SQL equality, so before normalization a snapshot ingested under the
    short id was invisible to the GUI's full-id lookup — surfacing as "no active
    snapshot" rather than as an error.
    """

    FULL = "APP@1777293133.OYEmP1.architecture-backend"
    SHORT = "APP@1777293133.OYEmP1"

    def test_snapshot_written_with_the_full_id_is_found_by_the_short_id(
        self, store: Any,
    ) -> None:
        _staging(store, "SNAP@1", anchor=self.FULL, request_id="req-1")
        store.complete_snapshot("SNAP@1")
        store.activate_snapshot("SNAP@1")

        active = store.get_active_snapshot(self.SHORT)
        assert active is not None
        assert active["snapshot_id"] == "SNAP@1"
        # Stored under the stable key, not the slugged form it arrived as.
        assert active["anchor_entity_id"] == self.SHORT

    def test_snapshot_written_with_the_short_id_is_found_by_the_full_id(
        self, store: Any,
    ) -> None:
        _staging(store, "SNAP@2", anchor=self.SHORT, request_id="req-2")
        store.complete_snapshot("SNAP@2")
        store.activate_snapshot("SNAP@2")

        active = store.get_active_snapshot(self.FULL)
        assert active is not None
        assert active["snapshot_id"] == "SNAP@2"

    def test_both_id_forms_are_the_same_replay_key(self, store: Any) -> None:
        """Otherwise the same logical ingest submitted via two surfaces would
        create two active snapshots for one entity."""
        _staging(store, "SNAP@3", anchor=self.FULL, request_id="req-3")

        assert store.find_snapshot_by_request(self.SHORT, "req-3") is not None
        assert store.find_snapshot_by_request(self.FULL, "req-3") is not None

    def test_listing_resolves_either_form(self, store: Any) -> None:
        _staging(store, "SNAP@4", anchor=self.SHORT, request_id="req-4")

        assert len(store.list_snapshots(anchor_entity_id=self.FULL)) == 1
        assert len(store.list_snapshots(anchor_entity_id=self.SHORT)) == 1

    def test_a_non_artifact_anchor_is_never_truncated(self, store: Any) -> None:
        """Synthetic anchors carry no slug to strip; truncating at the last dot
        would silently retarget them."""
        odd = "APP@live-check.some.thing"
        _staging(store, "SNAP@5", anchor=odd, request_id="req-5")

        assert store.find_snapshot_by_request(odd, "req-5") is not None
