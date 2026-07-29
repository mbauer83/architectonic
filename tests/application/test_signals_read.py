"""The active-snapshot signal read use case: exposure-filtered component/finding
listing (a finding is hidden when its component is) and the snapshot-model aggregate."""

from __future__ import annotations

from typing import Any

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.security_signals.signals_read import (
    list_active_components,
    list_active_findings,
    list_all_active_findings,
    signals_stats,
)


class _FakeStore:
    def __init__(self, snapshots: list[dict], components: dict[str, list], findings: dict[str, list]) -> None:
        self._snapshots = snapshots
        self._components = components
        self._findings = findings

    def get_active_snapshot(self, anchor_entity_id: str) -> dict[str, Any] | None:
        return next(
            (r for r in self._snapshots if r["anchor_entity_id"] == anchor_entity_id and r["status"] == "active"),
            None,
        )

    def list_snapshot_components(self, snapshot_id: str) -> list[dict[str, Any]]:
        return list(self._components.get(snapshot_id, []))

    def list_snapshot_findings(self, snapshot_id: str) -> list[dict[str, Any]]:
        return list(self._findings.get(snapshot_id, []))

    def list_snapshots(self, *, anchor_entity_id: str | None = None) -> list[dict[str, Any]]:
        return [r for r in self._snapshots if anchor_entity_id is None or r["anchor_entity_id"] == anchor_entity_id]


def _store() -> _FakeStore:
    return _FakeStore(
        snapshots=[
            {"snapshot_id": "R1", "anchor_entity_id": "APP@1", "status": "active"},
            {"snapshot_id": "R0", "anchor_entity_id": "APP@1", "status": "superseded"},
        ],
        components={"R1": [
            {"component_id": "C1", "name": "requests", "purl": "pkg:pypi/requests@2",
             "directness": "direct", "tlp": "TLP:AMBER"},
            {"component_id": "C2", "name": "secret-lib", "purl": "pkg:pypi/s@1", "tlp": "TLP:RED"},
        ]},
        findings={"R1": [
            {"finding_id": "F1", "component_id": "C1", "canonical_vulnerability_id": "V1",
             "severity_band": "high", "tlp": "TLP:AMBER"},
            {"finding_id": "F2", "component_id": "C2", "canonical_vulnerability_id": "V2",
             "severity_band": "critical", "tlp": "TLP:AMBER"},
        ]},
    )


_AMBER = AssuranceExposurePolicy("TLP:AMBER", True)


class TestComponents:
    def test_active_components_exposure_filtered(self) -> None:
        visible, withheld = list_active_components("APP@1", snapshot_store=_store(), policy=_AMBER)
        assert [c["component_id"] for c in visible] == ["C1"]  # C2 is TLP:RED
        assert withheld == 1

    def test_no_active_snapshot_is_empty(self) -> None:
        visible, withheld = list_active_components("APP@absent", snapshot_store=_store(), policy=_AMBER)
        assert visible == [] and withheld == 0


class TestFindings:
    def test_finding_on_hidden_component_is_hidden_with_it(self) -> None:
        # F2's component C2 is TLP:RED (hidden) → F2 is withheld even though F2's own tlp is AMBER.
        findings, withheld = list_active_findings("APP@1", snapshot_store=_store(), policy=_AMBER)
        assert [f["finding_id"] for f in findings] == ["F1"]
        assert withheld == 1
        assert findings[0]["assessed_entity_id"] == "APP@1"
        assert findings[0]["component_name"] == "requests"
        assert findings[0]["component_purl"] == "pkg:pypi/requests@2"

    def test_scope_to_one_component_by_purl(self) -> None:
        findings, _ = list_active_findings(
            "APP@1", snapshot_store=_store(), policy=_AMBER, purl="pkg:pypi/requests@2")
        assert [f["finding_id"] for f in findings] == ["F1"]

    def test_scope_to_absent_component_is_empty(self) -> None:
        findings, _ = list_active_findings(
            "APP@1", snapshot_store=_store(), policy=_AMBER, component_id="C-absent")
        assert findings == []


class TestStats:
    def test_aggregate_counts_over_active_snapshots(self) -> None:
        stats = signals_stats(snapshot_store=_store())
        assert stats["total_snapshots"] == 2
        assert stats["active_snapshots"] == 1
        assert stats["assessed_entity_count"] == 1
        assert stats["active_snapshot_bom_components"] == 2  # unfiltered operational count
        assert stats["active_snapshot_findings"] == 2

    def test_assessed_entities_enumerated(self) -> None:
        stats = signals_stats(snapshot_store=_store())
        assert stats["assessed_entities"] == [
            {"entity_id": "APP@1", "snapshot_id": "R1", "bom_component_count": 2, "finding_count": 2},
        ]


def _two_entity_store() -> _FakeStore:
    return _FakeStore(
        snapshots=[
            {"snapshot_id": "R1", "anchor_entity_id": "APP@backend", "status": "active"},
            {"snapshot_id": "R2", "anchor_entity_id": "APP@gui", "status": "active"},
        ],
        components={
            "R1": [{"component_id": "C1", "name": "requests", "purl": "pkg:pypi/requests@2", "tlp": "TLP:AMBER"}],
            "R2": [{"component_id": "C3", "name": "vue", "purl": "pkg:npm/vue@3", "tlp": "TLP:AMBER"}],
        },
        findings={
            "R1": [{"finding_id": "F1", "component_id": "C1", "canonical_vulnerability_id": "V1",
                    "severity_band": "high", "tlp": "TLP:AMBER"}],
            "R2": [{"finding_id": "F3", "component_id": "C3", "canonical_vulnerability_id": "V3",
                    "severity_band": "low", "tlp": "TLP:AMBER"}],
        },
    )


class TestAllActiveFindings:
    def test_findings_across_all_assessed_entities_are_tagged(self) -> None:
        findings, withheld = list_all_active_findings(snapshot_store=_two_entity_store(), policy=_AMBER)
        # Deterministic: assessed entities sorted, so backend (APP@backend) before gui (APP@gui).
        assert [(f["assessed_entity_id"], f["finding_id"]) for f in findings] == [
            ("APP@backend", "F1"),
            ("APP@gui", "F3"),
        ]
        assert withheld == 0
