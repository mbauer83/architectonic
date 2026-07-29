"""Failure-mode dimensions in the coverage report.

Both dimensions name a gap the row itself would only hint at: an effect that was never linked (so
severity cannot be derived and the row stays indeterminate) and a failure nothing detects (so
detectability sits at its worst). Listing them as coverage is what turns them from a quiet row
state into something a reviewer can count.

Traversal is deliberately **not** scoped to one analysis. A failure mode's hazards belong to the
STPA analysis that produced them, so a query that filtered the chain by `analysis_id` would report
every failure-mode analysis as incomplete.
"""

from __future__ import annotations

from typing import Any

from src.application.assurance_queries import coverage_gaps


def _node(node_id: str, node_type: str, **extra: object) -> dict[str, Any]:
    return {"node_id": node_id, "node_type": node_type, "name": node_id, **extra}


def _edge(source: str, conn_type: str, target: str) -> dict[str, Any]:
    return {"edge_id": f"{source}-{target}", "source_id": source,
            "conn_type": conn_type, "target_id": target}


class TestFailureModesWithoutAnEffect:
    def test_an_unlinked_failure_mode_is_a_gap(self) -> None:
        gaps = coverage_gaps([_node("FMD@1", "failure-mode")], [])

        assert [g["node_id"] for g in gaps["gaps"]["failure_modes_without_an_effect"]] == ["FMD@1"]

    def test_linking_an_effect_closes_it(self) -> None:
        nodes = [_node("FMD@1", "failure-mode"), _node("HAZ@1", "hazard")]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1")]

        gaps = coverage_gaps(nodes, edges)

        assert gaps["gaps"]["failure_modes_without_an_effect"] == []

    def test_the_hazard_may_belong_to_another_analysis(self) -> None:
        """The whole point of attaching to the existing spine: the hazard comes from the STPA work,
        so the link must count regardless of which analysis owns each end."""
        nodes = [
            _node("FMD@1", "failure-mode", analysis_id="FMEA@1"),
            _node("HAZ@1", "hazard", analysis_id="STPA@1"),
        ]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1")]

        assert coverage_gaps(nodes, edges)["gaps"]["failure_modes_without_an_effect"] == []


class TestFailureModesWithoutADetectionControl:
    def test_an_undetected_failure_mode_is_a_gap(self) -> None:
        gaps = coverage_gaps([_node("FMD@1", "failure-mode")], [])

        assert [
            g["node_id"] for g in gaps["gaps"]["failure_modes_without_a_detection_control"]
        ] == ["FMD@1"]

    def test_a_detection_control_closes_it(self) -> None:
        nodes = [_node("FMD@1", "failure-mode"), _node("ACN@1", "assurance-constraint")]
        edges = [_edge("ACN@1", "detects", "FMD@1")]

        gaps = coverage_gaps(nodes, edges)

        assert gaps["gaps"]["failure_modes_without_a_detection_control"] == []

    def test_direction_matters(self) -> None:
        """The control detects the failure mode, not the other way round."""
        nodes = [_node("FMD@1", "failure-mode"), _node("ACN@1", "assurance-constraint")]
        edges = [_edge("FMD@1", "detects", "ACN@1")]

        gaps = coverage_gaps(nodes, edges)

        assert gaps["gaps"]["failure_modes_without_a_detection_control"] != []


class TestTheReportStaysCoherent:
    def test_failure_mode_gaps_count_toward_the_total(self) -> None:
        gaps = coverage_gaps([_node("FMD@1", "failure-mode")], [])

        assert gaps["total_gaps"] == 2

    def test_a_store_with_no_failure_modes_reports_none_of_these(self) -> None:
        """A safety analysis that has not started an FMEA must not read as having gaps in one."""
        gaps = coverage_gaps([_node("HAZ@1", "hazard")], [])

        assert gaps["gaps"]["failure_modes_without_an_effect"] == []
        assert gaps["gaps"]["failure_modes_without_a_detection_control"] == []
