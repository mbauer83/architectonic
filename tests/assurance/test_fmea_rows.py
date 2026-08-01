"""The matrix: which rows exist, and what each cell says about itself.

Two things make this feature finishable rather than a death march, and both are asserted here.

**The candidate set is a nomination, not a census.** Every architecture element against five
guidewords is thousands of cells nobody completes; the elements a control structure already names
are a handful. Structure adds the ones nobody drew into a control structure — invisible to the
analysis, and known only to the architecture model.

**Three cell states, not two.** An empty cell that could mean either "nobody looked" or "someone
looked and found nothing" makes an unstarted analysis indistinguishable from a complete one.

Declared attributes are passed via `attributes` here, because that is where the store puts them.
These cases once set them as top-level keys and so passed against a node shape no store produces —
see `test_fmea_dismissal_through_the_store.py` for the same promises checked end to end.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.application.assurance.fmea_rows import candidates, matrix_rows
from src.domain.assurance.failure_modes import NOT_CREDIBLE, RECORDED, UNTOUCHED
from src.domain.assurance.fmea_factors import FactorAssessment
from src.domain.assurance.fmea_structural_signals import TypedEdge


@dataclass(frozen=True)
class _TypeInfo:
    derivation_role: str | None
    derivation_strength: int | None


def _typed(source: str, target: str, connection_type: str = "archimate-serving") -> TypedEdge:
    return TypedEdge(
        connection_id=f"{source}-{target}", source_id=source, target_id=target,
        connection_type=connection_type, role="dependency", strength=4,
    )


def _node(node_id: str, node_type: str, **fields: object) -> dict[str, Any]:
    attributes = fields.pop("attributes", None)
    node: dict[str, Any] = {"node_id": node_id, "node_type": node_type, "name": node_id, **fields}
    if attributes is not None:
        node["attributes_json"] = json.dumps(attributes)
    return node


def _ref(node_id: str, element_id: str) -> dict[str, Any]:
    return {"assurance_node_id": node_id, "arch_artifact_id": element_id, "ref_type": "binds-to"}


def _edge(source: str, conn_type: str, target: str) -> dict[str, Any]:
    return {"edge_id": f"{source}-{target}", "source_id": source,
            "conn_type": conn_type, "target_id": target}


class TestTheCandidateSetIsBounded:
    def test_control_structure_elements_are_nominated(self) -> None:
        nodes = [_node("CSN@1", "control-structure-node")]

        found = candidates(nodes=nodes, arch_refs=[_ref("CSN@1", "APP@store")])

        assert [c.element_id for c in found] == ["APP@store"]
        assert found[0].nominated_by == ("control-structure",)

    def test_an_element_the_analysis_named_is_listed_once(self) -> None:
        nodes = [_node("CSN@1", "control-structure-node"), _node("CSN@2", "control-structure-node")]

        found = candidates(
            nodes=nodes,
            arch_refs=[_ref("CSN@1", "APP@store"), _ref("CSN@2", "APP@store")],
        )

        assert [c.element_id for c in found] == ["APP@store"]
        assert found[0].nominated_by == ("control-structure",)

    def test_an_element_the_analysis_never_named_is_not_offered(self) -> None:
        """However load-bearing the graph shows it to be.

        Measured on the repository this software describes, nominating them produced 107 rows beside
        the 3 the analysis had reached. The claim still reaches a reader — as a verification finding
        carrying what relies on the element — and acting on it means naming the element deliberately.
        """
        found = candidates(nodes=[], arch_refs=[])

        assert found == ()

    def test_only_a_control_structure_node_nominates(self) -> None:
        """A failure mode bound to an element does not itself put that element on the list; the
        control structure is what says the element is in scope."""
        nodes = [_node("FMD@1", "failure-mode")]

        found = candidates(nodes=nodes, arch_refs=[_ref("FMD@1", "APP@store")])

        assert found == ()

    def test_nothing_modelled_offers_nothing(self) -> None:
        assert candidates(nodes=[], arch_refs=[]) == ()


class TestEveryCandidateGetsFiveCells:
    def _rows(self, nodes: list[dict[str, Any]], refs: list[dict[str, Any]], edges: list[dict[str, Any]]) -> Any:
        return matrix_rows(nodes=nodes, edges=edges, arch_refs=refs, assessments={})

    def test_a_candidate_with_no_failure_modes_is_all_untouched(self) -> None:
        nodes = [_node("CSN@1", "control-structure-node")]

        rows = self._rows(nodes, [_ref("CSN@1", "APP@store")], [])

        assert len(rows[0]["cells"]) == 5
        assert {c["state"] for c in rows[0]["cells"]} == {UNTOUCHED}
        assert rows[0]["unanswered_cells"] == 5

    def test_an_untouched_cell_states_what_would_advance_it(self) -> None:
        """No reader should have to run a verifier and map a code back to a row."""
        nodes = [_node("CSN@1", "control-structure-node")]

        rows = self._rows(nodes, [_ref("CSN@1", "APP@store")], [])

        assert "dismiss it as not credible" in rows[0]["cells"][0]["next_action"]

    def test_a_recorded_failure_mode_fills_its_own_cell_only(self) -> None:
        nodes = [
            _node("CSN@1", "control-structure-node"),
            _node("FMD@1", "failure-mode", failure_type="no-function"),
        ]
        refs = [_ref("CSN@1", "APP@store"), _ref("FMD@1", "APP@store")]

        rows = self._rows(nodes, refs, [])

        by_guideword = {c["guideword"]: c for c in rows[0]["cells"]}
        assert by_guideword["no-function"]["state"] == RECORDED
        assert by_guideword["partial-function"]["state"] == UNTOUCHED

    def test_a_dismissal_counts_as_answered_and_carries_who_and_why(self) -> None:
        """Dismissing must be as cheap as filling in, or analysts write filler to look finished."""
        nodes = [
            _node("CSN@1", "control-structure-node"),
            _node(
                "FMD@1", "failure-mode", failure_type="excessive-function",
                attributes={
                    "assessment_state": NOT_CREDIBLE,
                    "dismissed_by": "analyst",
                    "dismissal_rationale": "the component cannot run faster than its input",
                },
            ),
        ]
        refs = [_ref("CSN@1", "APP@store"), _ref("FMD@1", "APP@store")]

        rows = self._rows(nodes, refs, [])

        cell = next(c for c in rows[0]["cells"] if c["guideword"] == "excessive-function")
        assert cell["state"] == NOT_CREDIBLE
        assert cell["dismissal"]["by"] == "analyst"
        assert rows[0]["answered_cells"] == 1

    def test_a_dismissed_cell_needs_no_further_action(self) -> None:
        nodes = [
            _node("CSN@1", "control-structure-node"),
            _node(
                "FMD@1", "failure-mode", failure_type="no-function",
                attributes={"assessment_state": NOT_CREDIBLE},
            ),
        ]
        refs = [_ref("CSN@1", "APP@store"), _ref("FMD@1", "APP@store")]

        rows = self._rows(nodes, refs, [])

        cell = next(c for c in rows[0]["cells"] if c["guideword"] == "no-function")
        assert cell["next_action"] == ""


class TestWhatARecordedCellReports:
    def _recorded_row(self, *, severity: str | None) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = [
            _node("CSN@1", "control-structure-node"),
            _node("FMD@1", "failure-mode", failure_type="no-function"),
        ]
        edges: list[dict[str, Any]] = []
        if severity is not None:
            nodes += [_node("HAZ@1", "hazard"), _node("LSS@1", "loss", attributes={"severity": severity})]
            edges = [_edge("FMD@1", "leads-to", "HAZ@1"), _edge("HAZ@1", "leads-to", "LSS@1")]
        refs = [_ref("CSN@1", "APP@store"), _ref("FMD@1", "APP@store")]
        rows = matrix_rows(nodes=nodes, edges=edges, arch_refs=refs, assessments={})
        return next(c for c in rows[0]["cells"] if c["guideword"] == "no-function")

    def test_an_unlinked_effect_leaves_severity_absent_and_says_so(self) -> None:
        cell = self._recorded_row(severity=None)

        assert cell["factors"]["severity"]["value"] is None
        assert "Link an effect" in cell["next_action"]

    def test_a_linked_effect_derives_severity(self) -> None:
        cell = self._recorded_row(severity="catastrophic")

        assert cell["factors"]["severity"]["value"] == "catastrophic"
        assert cell["factors"]["severity"]["basis"] == "derived"

    def test_a_row_with_no_detection_control_says_that_is_the_gap(self) -> None:
        cell = self._recorded_row(severity="catastrophic")

        assert cell["factors"]["detectability"]["value"] == "very-low"
        assert "Nothing detects this failure" in cell["next_action"]

    def test_occurrence_is_not_requested_where_it_cannot_change_the_band(self) -> None:
        """Catastrophic and undetected is high whatever the rate, so the field is not rendered."""
        cell = self._recorded_row(severity="catastrophic")

        assert cell["occurrence_is_requested"] is False
        assert cell["action_priority"] == "high"

    def test_such_a_row_is_complete_with_no_numeric_input_at_all(self) -> None:
        """Naming the failure and linking its effect was the whole job."""
        cell = self._recorded_row(severity="catastrophic")

        assert cell["action_priority"] != "indeterminate"
        assert cell["factors"]["occurrence"]["value"] is None


class TestTheRowRollsUp:
    def test_the_worst_band_across_the_row_is_reported(self) -> None:
        nodes = [
            _node("CSN@1", "control-structure-node"),
            _node("FMD@1", "failure-mode", failure_type="no-function"),
            _node("HAZ@1", "hazard"),
            _node("LSS@1", "loss", attributes={"severity": "catastrophic"}),
        ]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1"), _edge("HAZ@1", "leads-to", "LSS@1")]
        refs = [_ref("CSN@1", "APP@store"), _ref("FMD@1", "APP@store")]

        rows = matrix_rows(nodes=nodes, edges=edges, arch_refs=refs, assessments={})

        assert rows[0]["worst_action_priority"] == "high"

    def test_a_row_with_no_failure_modes_rolls_up_to_nothing(self) -> None:
        """Not `low`: an un-analysed element must not read as a quiet one."""
        nodes = [_node("CSN@1", "control-structure-node")]

        rows = matrix_rows(nodes=nodes, edges=[], arch_refs=[_ref("CSN@1", "APP@store")], assessments={})

        assert rows[0]["worst_action_priority"] is None


class TestACellPublishesWhatRecordingAJudgementNeeds:
    """`assurance_set_fmea_factor` refuses a judgement without the digest of the model picture it
    was made against, and an assessment applies only while that digest still matches. So the digest
    has to be readable from the matrix — the surface the tool's own guidance points a caller at.

    Without it the tool is unusable for its main purpose: occurrence is asserted-only, so there is no
    derived value to fall back on, and a judgement filed against a digest that never matched is
    retained but never applies. The row then stays undecidable however carefully it was judged.
    """

    def _cell(self, guideword: str = "no-function") -> dict[str, Any]:
        nodes = [
            _node("CSN@1", "control-structure-node"),
            _node("FMD@1", "failure-mode", failure_type=guideword),
            _node("HAZ@1", "hazard"),
            _node("LSS@1", "loss", attributes={"severity": "major"}),
        ]
        refs = [_ref("CSN@1", "APP@store"), _ref("FMD@1", "APP@store")]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1"), _edge("HAZ@1", "leads-to", "LSS@1")]
        rows = matrix_rows(nodes=nodes, edges=edges, arch_refs=refs, assessments={})
        cells = rows[0]["cells"]
        assert isinstance(cells, list)
        return next(c for c in cells if c["guideword"] == guideword)

    def test_every_factor_carries_its_basis_digest(self) -> None:
        factors = self._cell()["factors"]

        for name in ("severity", "occurrence", "detectability"):
            assert factors[name]["basis_digest"], f"{name} publishes no digest to record against"

    def test_a_derived_factor_digest_is_stable_between_reads(self) -> None:
        """A digest that varied per read would make every judgement stale the moment it was filed."""
        assert self._cell()["factors"]["severity"]["basis_digest"] == (
            self._cell()["factors"]["severity"]["basis_digest"]
        )

    def test_the_published_digest_is_the_one_an_assessment_is_matched_against(self) -> None:
        """The contract in one assertion: record against the digest the cell published, and the
        judgement applies."""
        digest = self._cell()["factors"]["occurrence"]["basis_digest"]
        nodes = [
            _node("CSN@1", "control-structure-node"),
            _node("FMD@1", "failure-mode", failure_type="no-function"),
            _node("HAZ@1", "hazard"),
            _node("LSS@1", "loss", attributes={"severity": "major"}),
        ]
        refs = [_ref("CSN@1", "APP@store"), _ref("FMD@1", "APP@store")]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1"), _edge("HAZ@1", "leads-to", "LSS@1")]
        judged = FactorAssessment(
            node_id="FMD@1", factor="occurrence", basis_digest=digest, revision=1,
            value="likely", justification="observed twice in a fortnight", author="analyst",
            created_at="2026-07-26T00:00:00Z",
        )

        rows = matrix_rows(
            nodes=nodes, edges=edges, arch_refs=refs, assessments={"FMD@1": [judged]},
        )
        cells = rows[0]["cells"]
        assert isinstance(cells, list)
        cell = next(c for c in cells if c["guideword"] == "no-function")

        assert cell["factors"]["occurrence"]["value"] == "likely"
        assert cell["factors"]["occurrence"]["basis"] == "asserted"
