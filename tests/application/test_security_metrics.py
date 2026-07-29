"""Security metrics: filter-before-aggregate over mixed-TLP rows (a hidden row
must never influence any count, maximum, band, suppression, or
classification), closed content states, VEX suppression with
visibility-before-suppression, and the unit-explicit vocabulary."""

from __future__ import annotations

from typing import Any

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.security_signals.metrics import compute_security_metrics

RUN = {"snapshot_id": "SNAP@1", "activated_at": "2026-07-20T00:00:00Z", "tlp": "TLP:AMBER"}


class FakeSnapshotReads:
    def __init__(self, snapshot: dict[str, Any] | None, components: list[dict[str, Any]],
                 findings: list[dict[str, Any]]) -> None:
        self._snapshot, self._components, self._findings = snapshot, components, findings

    def get_active_snapshot(self, anchor_entity_id: str) -> dict[str, Any] | None:
        return self._snapshot

    def list_snapshot_components(self, snapshot_id: str) -> list[dict[str, Any]]:
        return list(self._components)

    def list_snapshot_findings(self, snapshot_id: str) -> list[dict[str, Any]]:
        return list(self._findings)


class FakeVexReads:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def list_anchor_assessments(self, anchor_entity_id: str) -> list[dict[str, Any]]:
        return list(self._rows)


def _component(cid: str, *, purl: str = "", directness: str = "direct",
               tlp: str = "TLP:AMBER") -> dict[str, Any]:
    return {"component_id": cid, "purl": purl or f"pkg:pypi/{cid}@1", "name": cid,
            "directness": directness, "tlp": tlp}


def _finding(cid: str, vuln: str, *, band: str = "high", score: float | None = 7.5,
             applicability: str = "applicable", tlp: str = "TLP:AMBER") -> dict[str, Any]:
    return {"finding_id": f"F-{cid}-{vuln}", "component_id": cid,
            "canonical_vulnerability_id": vuln, "severity_band": band,
            "cvss_score": score, "applicability": applicability, "tlp": tlp}


def _vex(purl: str, vuln: str, revision: int, vex_status: str,
         tlp: str = "TLP:AMBER") -> dict[str, Any]:
    return {"canonical_component_id": purl, "canonical_vulnerability_id": vuln,
            "revision": revision, "vex_status": vex_status, "tlp": tlp}


def _metrics(components: list, findings: list, vex: list | None = None,
             ceiling: str = "TLP:RED", snapshot: dict | None = RUN) -> Any:
    return compute_security_metrics(
        "APP@1",
        snapshot_store=FakeSnapshotReads(snapshot, components, findings),
        vex_store=FakeVexReads(vex),
        policy=AssuranceExposurePolicy(ceiling, True),
    )


class TestContentStates:
    def test_no_active_snapshot(self) -> None:
        result = _metrics([], [], snapshot=None)
        assert result.content_state == "no_active_snapshot"
        assert result.basis_snapshot_id is None

    def test_no_findings_is_distinct_from_hidden_findings(self) -> None:
        clean = _metrics([_component("a")], [])
        assert clean.content_state == "no_findings"
        hidden = _metrics(
            [_component("a")],
            [_finding("a", "VID@1", tlp="TLP:RED")],
            ceiling="TLP:AMBER",
        )
        assert hidden.content_state == "visibility_limited"
        assert hidden.finding_total == 0  # never "zero vulnerabilities, all clear"

    def test_complete_when_nothing_is_hidden_at_red_ceiling(self) -> None:
        result = _metrics([_component("a")], [_finding("a", "VID@1")])
        assert result.content_state == "complete"
        assert result.basis_snapshot_id == "SNAP@1"

    def test_ceiling_below_top_is_not_visibility_limited_when_nothing_withheld(self) -> None:
        # AMBER data at an AMBER ceiling: everything is returned, so the flag must be
        # False even though the ceiling sits below the top level (no misleading banner).
        result = _metrics(
            [_component("a", tlp="TLP:AMBER")],
            [_finding("a", "VID@1", tlp="TLP:AMBER")],
            ceiling="TLP:AMBER",
        )
        assert result.content_state == "complete"
        assert result.visibility_limited is False

    def test_no_active_snapshot_is_not_visibility_limited(self) -> None:
        result = _metrics([], [], ceiling="TLP:AMBER", snapshot=None)
        assert result.content_state == "no_active_snapshot"
        assert result.visibility_limited is False


class TestFilterBeforeAggregate:
    def test_hidden_rows_influence_no_count_max_band_or_classification(self) -> None:
        components = [
            _component("a", tlp="TLP:AMBER"),
            _component("secret", tlp="TLP:RED"),
        ]
        findings = [
            _finding("a", "VID@1", band="medium", score=5.0),
            _finding("secret", "VID@2", band="critical", score=9.9, tlp="TLP:RED"),
            _finding("a", "VID@3", band="critical", score=9.8, tlp="TLP:RED"),
        ]
        result = _metrics(components, findings, ceiling="TLP:AMBER")
        assert result.component_count == 1
        assert result.finding_total == 1
        assert result.max_cvss_score == 5.0
        assert result.max_severity_band == "medium"
        assert result.severity_band_counts == {"medium": 1}
        assert result.distinct_open_vulnerabilities == 1
        assert result.computed_classification == "TLP:AMBER"  # max of VISIBLE only
        assert result.visibility_limited is True

    def test_finding_on_a_hidden_component_is_hidden_with_it(self) -> None:
        components = [_component("secret", tlp="TLP:RED")]
        findings = [_finding("secret", "VID@1", band="critical", tlp="TLP:AMBER")]
        result = _metrics(components, findings, ceiling="TLP:AMBER")
        assert result.finding_total == 0
        assert result.content_state == "visibility_limited"


class TestVexSuppression:
    PURL = "pkg:pypi/a@1"

    def test_only_current_suppressing_revision_closes_the_finding(self) -> None:
        vex = [
            _vex(self.PURL, "VID@1", 1, "not_affected"),
            _vex(self.PURL, "VID@1", 2, "affected"),  # latest wins → reopened
        ]
        result = _metrics([_component("a", purl=self.PURL)], [_finding("a", "VID@1")], vex)
        assert result.suppressed_finding_count == 0
        assert result.distinct_open_vulnerabilities == 1

    def test_suppressing_revision_closes_it_and_counts_it(self) -> None:
        vex = [_vex(self.PURL, "VID@1", 1, "fixed")]
        result = _metrics([_component("a", purl=self.PURL)], [_finding("a", "VID@1")], vex)
        assert result.suppressed_finding_count == 1
        assert result.finding_total == 1  # visible finding, suppressed for openness
        assert result.distinct_open_vulnerabilities == 0
        assert result.open_component_findings == {}

    def test_hidden_vex_never_suppresses_a_visible_finding(self) -> None:
        vex = [_vex(self.PURL, "VID@1", 1, "not_affected", tlp="TLP:RED")]
        result = _metrics(
            [_component("a", purl=self.PURL)], [_finding("a", "VID@1")], vex,
            ceiling="TLP:AMBER",
        )
        assert result.suppressed_finding_count == 0
        assert result.distinct_open_vulnerabilities == 1


class TestVocabulary:
    def test_directness_partition_sums_to_open_findings(self) -> None:
        components = [
            _component("a", directness="direct"),
            _component("b", directness="transitive"),
            _component("c", directness="unknown"),
        ]
        findings = [
            _finding("a", "VID@1"), _finding("b", "VID@2"), _finding("c", "VID@3"),
            _finding("b", "VID@4"),
        ]
        result = _metrics(components, findings)
        assert result.open_component_findings == {"direct": 1, "transitive": 2, "unknown": 1}
        assert sum(result.open_component_findings.values()) == result.finding_total

    def test_distinct_vulnerabilities_deduplicate_across_components(self) -> None:
        components = [_component("a"), _component("b")]
        findings = [_finding("a", "VID@same"), _finding("b", "VID@same")]
        result = _metrics(components, findings)
        assert result.finding_total == 2  # component findings
        assert result.distinct_open_vulnerabilities == 1  # canonical identities

    def test_unknown_severity_and_applicability_are_counted_never_scored(self) -> None:
        findings = [
            _finding("a", "VID@1", band="", score=None, applicability="unknown"),
            _finding("a", "VID@2", band="weird-band", score=None),
        ]
        result = _metrics([_component("a")], findings)
        assert result.unknown_severity_finding_count == 2
        assert result.applicability_unknown_count == 1
        assert result.max_cvss_score is None
        assert result.max_severity_band is None
