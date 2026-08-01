"""Severity and detectability derived from the assurance graph, and what absence means.

Two asymmetries are deliberate and are what these tests pin.

Severity is **absent** when no loss is reachable, because an unlinked failure mode has no known
consequence and calling that `negligible` would make a coverage gap look like a finding of safety.

Detectability is **never absent** — "nothing detects this" is itself the answer, and the weakest
band says it. Absence there would read as "not yet assessed", which is a much softer claim than the
truth.
"""

from __future__ import annotations

import json
from typing import Any

from src.application.assurance.fmea_derivation import (
    CONTROL_ONLY,
    EVIDENCED,
    NO_CONTROL,
    PIPELINE_EXERCISED,
    SEALED,
    derive_factors,
)
from src.domain.assurance.fmea_factors import DETECTABILITY_SCALE


def _node(node_id: str, node_type: str, **attributes: object) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "name": node_id,
        "attributes_json": json.dumps(attributes),
    }


def _edge(source: str, conn_type: str, target: str) -> dict[str, Any]:
    return {"edge_id": f"{source}-{conn_type}-{target}", "source_id": source,
            "conn_type": conn_type, "target_id": target}


class TestSeverityComesFromTheReachableLosses:
    def test_the_worst_reachable_loss_decides(self) -> None:
        nodes = [
            _node("FMD@1", "failure-mode"),
            _node("HAZ@1", "hazard"), _node("HAZ@2", "hazard"),
            _node("LSS@1", "loss", severity="minor"),
            _node("LSS@2", "loss", severity="catastrophic"),
        ]
        edges = [
            _edge("FMD@1", "leads-to", "HAZ@1"), _edge("FMD@1", "leads-to", "HAZ@2"),
            _edge("HAZ@1", "leads-to", "LSS@1"), _edge("HAZ@2", "leads-to", "LSS@2"),
        ]

        result = derive_factors("FMD@1", nodes=nodes, edges=edges)

        assert result.severity.value == "catastrophic"

    def test_the_worst_is_ranked_not_sorted_alphabetically(self) -> None:
        """`catastrophic` < `minor` as text. Without the ordinal scale this returns `minor`."""
        nodes = [
            _node("FMD@1", "failure-mode"), _node("HAZ@1", "hazard"),
            _node("LSS@1", "loss", severity="catastrophic"),
            _node("LSS@2", "loss", severity="minor"),
        ]
        edges = [
            _edge("FMD@1", "leads-to", "HAZ@1"),
            _edge("HAZ@1", "leads-to", "LSS@1"), _edge("HAZ@1", "leads-to", "LSS@2"),
        ]

        assert derive_factors("FMD@1", nodes=nodes, edges=edges).severity.value == "catastrophic"

    def test_an_unlinked_failure_mode_has_no_severity(self) -> None:
        """A coverage gap, not a mild finding."""
        nodes = [_node("FMD@1", "failure-mode")]

        result = derive_factors("FMD@1", nodes=nodes, edges=[])

        assert result.severity.value is None

    def test_a_hazard_with_no_loss_yields_no_severity(self) -> None:
        nodes = [_node("FMD@1", "failure-mode"), _node("HAZ@1", "hazard")]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1")]

        assert derive_factors("FMD@1", nodes=nodes, edges=edges).severity.value is None

    def test_a_loss_with_no_severity_recorded_contributes_nothing(self) -> None:
        nodes = [
            _node("FMD@1", "failure-mode"), _node("HAZ@1", "hazard"), _node("LSS@1", "loss"),
        ]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1"), _edge("HAZ@1", "leads-to", "LSS@1")]

        assert derive_factors("FMD@1", nodes=nodes, edges=edges).severity.value is None

    def test_the_chain_does_not_run_backwards(self) -> None:
        """`leads-to` is directional; a hazard that leads to this failure mode is not its effect."""
        nodes = [
            _node("FMD@1", "failure-mode"), _node("HAZ@1", "hazard"),
            _node("LSS@1", "loss", severity="major"),
        ]
        edges = [_edge("HAZ@1", "leads-to", "FMD@1"), _edge("HAZ@1", "leads-to", "LSS@1")]

        assert derive_factors("FMD@1", nodes=nodes, edges=edges).severity.value is None

    def test_the_witness_shows_the_path(self) -> None:
        nodes = [
            _node("FMD@1", "failure-mode"), _node("HAZ@1", "hazard"),
            _node("LSS@1", "loss", severity="major"),
        ]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1"), _edge("HAZ@1", "leads-to", "LSS@1")]

        witness = derive_factors("FMD@1", nodes=nodes, edges=edges).severity.witness

        assert witness == ("FMD@1 --leads-to--> HAZ@1 --leads-to--> LSS@1 (major)",)


class TestDetectabilityComesFromTheDetectionControls:
    def test_nothing_detecting_it_is_the_weakest_band(self) -> None:
        nodes = [_node("FMD@1", "failure-mode")]

        result = derive_factors("FMD@1", nodes=nodes, edges=[])

        assert result.detectability.value == NO_CONTROL
        assert result.detectability.value is not None, "absence would read as 'not yet assessed'"

    def test_an_unevidenced_control_lifts_it_one_band(self) -> None:
        nodes = [_node("FMD@1", "failure-mode"), _node("ACN@1", "assurance-constraint")]
        edges = [_edge("ACN@1", "detects", "FMD@1")]

        assert derive_factors("FMD@1", nodes=nodes, edges=edges).detectability.value == CONTROL_ONLY

    def test_an_evidenced_control_lifts_it_further(self) -> None:
        nodes = [
            _node("FMD@1", "failure-mode"), _node("ACN@1", "assurance-constraint"),
            _node("EVD@1", "evidence"),
        ]
        edges = [_edge("ACN@1", "detects", "FMD@1"), _edge("ACN@1", "evidenced-by", "EVD@1")]

        assert derive_factors("FMD@1", nodes=nodes, edges=edges).detectability.value == EVIDENCED

    def test_an_architecture_evidence_reference_also_counts(self) -> None:
        """The lightweight alternative to an evidence node substantiates the control just as well."""
        nodes = [_node("FMD@1", "failure-mode"), _node("ACN@1", "assurance-constraint")]
        edges = [_edge("ACN@1", "detects", "FMD@1")]

        result = derive_factors(
            "FMD@1", nodes=nodes, edges=edges, evidenced_ref_ids=frozenset({"ACN@1"}),
        )

        assert result.detectability.value == EVIDENCED

    def test_evidence_inside_a_sealed_baseline_lifts_it_again(self) -> None:
        nodes = [
            _node("FMD@1", "failure-mode"), _node("ACN@1", "assurance-constraint"),
            _node("EVD@1", "evidence"),
        ]
        edges = [_edge("ACN@1", "detects", "FMD@1"), _edge("ACN@1", "evidenced-by", "EVD@1")]

        result = derive_factors(
            "FMD@1", nodes=nodes, edges=edges, sealed_evidence_ids=frozenset({"EVD@1"}),
        )

        assert result.detectability.value == SEALED

    def test_evidence_naming_a_quality_gate_reaches_the_strongest_band(self) -> None:
        """A control an automated gate exercises is caught without anyone remembering to look."""
        nodes = [
            _node("FMD@1", "failure-mode"), _node("ACN@1", "assurance-constraint"),
            _node("EVD@1", "evidence", gate="backend quality gate"),
        ]
        edges = [_edge("ACN@1", "detects", "FMD@1"), _edge("ACN@1", "evidenced-by", "EVD@1")]

        result = derive_factors("FMD@1", nodes=nodes, edges=edges)

        assert result.detectability.value == PIPELINE_EXERCISED

    def test_the_best_control_decides_among_several(self) -> None:
        nodes = [
            _node("FMD@1", "failure-mode"),
            _node("ACN@1", "assurance-constraint"), _node("ACN@2", "assurance-constraint"),
            _node("EVD@1", "evidence"),
        ]
        edges = [
            _edge("ACN@1", "detects", "FMD@1"),
            _edge("ACN@2", "detects", "FMD@1"), _edge("ACN@2", "evidenced-by", "EVD@1"),
        ]

        assert derive_factors("FMD@1", nodes=nodes, edges=edges).detectability.value == EVIDENCED

    def test_detection_direction_matters(self) -> None:
        """The control detects the failure mode, not the other way round."""
        nodes = [_node("FMD@1", "failure-mode"), _node("ACN@1", "assurance-constraint")]
        edges = [_edge("FMD@1", "detects", "ACN@1")]

        assert derive_factors("FMD@1", nodes=nodes, edges=edges).detectability.value == NO_CONTROL

    def test_the_bands_are_the_declared_scale(self) -> None:
        assert (NO_CONTROL, CONTROL_ONLY, EVIDENCED, SEALED, PIPELINE_EXERCISED) == DETECTABILITY_SCALE


class TestDeclaredTelemetryNeverRaisesTheBand:
    def test_a_heavily_instrumented_component_still_has_no_detectability_without_a_control(
        self,
    ) -> None:
        """The rule that keeps detectability meaning what it says: emitting logs is not evidence
        that THIS failure gets noticed."""
        nodes = [_node("FMD@1", "failure-mode", Telemetry="Synthetic Probing")]

        assert derive_factors("FMD@1", nodes=nodes, edges=[]).detectability.value == NO_CONTROL

    def test_the_derivation_never_reads_a_telemetry_attribute(self) -> None:
        """Structural: no executable line names it, so no branch can key on it. Prose is excluded —
        the module docstring names it precisely to say it is not an input."""
        import ast
        import inspect

        from src.application.assurance import fmea_derivation

        tree = ast.parse(inspect.getsource(fmea_derivation))
        docstring_nodes = {
            id(holder.body[0].value)
            for holder in ast.walk(tree)
            if isinstance(holder, (ast.Module, ast.ClassDef, ast.FunctionDef))
            and holder.body
            and isinstance(holder.body[0], ast.Expr)
            and isinstance(holder.body[0].value, ast.Constant)
        }
        code_literals = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_nodes
        ]

        assert not [text for text in code_literals if "elemetry" in text]
        assert not [
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and "elemetry" in node.attr
        ]


class TestTheBasisDigest:
    def test_each_factor_gets_its_own_digest(self) -> None:
        nodes = [_node("FMD@1", "failure-mode")]

        digests = derive_factors("FMD@1", nodes=nodes, edges=[]).digests

        assert set(digests) == {"severity", "occurrence", "detectability"}

    def test_swapping_a_loss_for_one_of_equal_severity_moves_the_digest(self) -> None:
        """The case a value comparison cannot see, and the reason the digest exists."""
        def _with_loss(loss_id: str) -> str:
            nodes = [
                _node("FMD@1", "failure-mode"), _node("HAZ@1", "hazard"),
                _node(loss_id, "loss", severity="major"),
            ]
            edges = [_edge("FMD@1", "leads-to", "HAZ@1"), _edge("HAZ@1", "leads-to", loss_id)]
            result = derive_factors("FMD@1", nodes=nodes, edges=edges)
            assert result.severity.value == "major"
            return result.digests["severity"]

        assert _with_loss("LSS@1") != _with_loss("LSS@2")

    def test_an_unchanged_model_digests_the_same(self) -> None:
        nodes = [
            _node("FMD@1", "failure-mode"), _node("HAZ@1", "hazard"),
            _node("LSS@1", "loss", severity="major"),
        ]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1"), _edge("HAZ@1", "leads-to", "LSS@1")]

        first = derive_factors("FMD@1", nodes=nodes, edges=edges).digests
        second = derive_factors("FMD@1", nodes=nodes, edges=edges).digests

        assert first == second

    def test_an_occurrence_rationale_s_citations_form_its_digest(self) -> None:
        """Occurrence has no derived value but does have a basis, so a judgement about it retires
        when what it cited changes."""
        nodes = [_node("FMD@1", "failure-mode")]

        cited = derive_factors(
            "FMD@1", nodes=nodes, edges=[], occurrence_basis=["APP@1:single-point-of-failure"],
        ).digests["occurrence"]
        uncited = derive_factors("FMD@1", nodes=nodes, edges=[]).digests["occurrence"]

        assert cited != uncited
