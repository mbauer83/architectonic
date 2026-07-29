"""The failure-mode matrix type: store-projected, table-only, and scoped to what a cell shows.

The invariant that matters most is the first one. A failure-mode matrix is built from confidential
store content, so it must never appear in the file-backed diagram browser — there is no artifact on
disk to list, and a listing that offered one would be offering a handle to confidential material.
That exclusion is not a hand-kept list of names: it follows from the type implementing the
store-projection capability, which is exactly why it is asserted through the capability rather than
by comparing strings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.diagram_types.fmea_matrix import module as fmea_matrix
from src.domain.modules.catalogs import DiagramTypeCatalogImpl
from src.infrastructure.app_bootstrap import build_module_registry, complete_diagram_type_catalog


def _node(node_id: str, node_type: str) -> dict[str, object]:
    return {"node_id": node_id, "node_type": node_type, "name": node_id}


def _edge(source: str, conn_type: str, target: str) -> dict[str, object]:
    return {"edge_id": f"{source}-{target}", "source_id": source,
            "conn_type": conn_type, "target_id": target}


class TestItIsStoreProjectedAndSoNeverFileListed:
    def test_the_capability_reports_it_as_store_projected(self) -> None:
        catalog = DiagramTypeCatalogImpl(build_module_registry(complete_vocabulary=True))

        assert "fmea-matrix" in catalog.store_projected_diagram_types()

    def test_it_keeps_the_company_of_the_other_store_projected_types(self) -> None:
        """Sanity on the mechanism: the UCA matrix is projected the same way."""
        catalog = DiagramTypeCatalogImpl(build_module_registry(complete_vocabulary=True))

        assert {"fmea-matrix", "uca-matrix"} <= catalog.store_projected_diagram_types()


class TestItRefusesToRenderPlantUml:
    def test_render_body_raises(self) -> None:
        """Not "returns empty" — raising is what stops the PUML pipeline being pointed at it."""
        with pytest.raises(ValueError, match="grid renderer"):
            fmea_matrix.renderer.render_body(
                "any", [], [], "fmea-matrix", Path("/nonexistent"),
            )

    def test_it_declares_a_reader_facing_label_and_description(self) -> None:
        """The presentation contract: a type with no label shows up as its slug."""
        ui = complete_diagram_type_catalog().all_diagram_types()["fmea-matrix"].ui_config

        assert ui.label == "FMEA Matrix"
        assert ui.description.strip()


class TestTheProjectionIsScopedToWhatACellShows:
    def test_failure_modes_and_their_chain_are_included(self) -> None:
        nodes = [
            _node("FMD@1", "failure-mode"), _node("HAZ@1", "hazard"),
            _node("LSS@1", "loss"), _node("ACN@1", "assurance-constraint"),
        ]
        edges = [_edge("FMD@1", "leads-to", "HAZ@1"), _edge("ACN@1", "detects", "FMD@1")]

        projected_nodes, projected_edges = fmea_matrix.project_store_graph(nodes, edges)

        assert {str(n["node_id"]) for n in projected_nodes} == {"FMD@1", "HAZ@1", "LSS@1", "ACN@1"}
        assert len(projected_edges) == 2

    def test_control_structure_content_is_left_out(self) -> None:
        """The loop belongs to the control-structure view; here it would add cells nothing reads."""
        nodes = [_node("FMD@1", "failure-mode"), _node("CSN@1", "control-structure-node")]

        projected_nodes, _ = fmea_matrix.project_store_graph(nodes, [])

        assert {str(n["node_id"]) for n in projected_nodes} == {"FMD@1"}

    def test_relations_that_place_nothing_in_a_cell_are_left_out(self) -> None:
        nodes = [_node("ACN@1", "assurance-constraint"), _node("LSS@1", "loss")]
        edges = [_edge("ACN@1", "mitigates", "LSS@1")]

        _, projected_edges = fmea_matrix.project_store_graph(nodes, edges)

        assert projected_edges == []

    def test_an_edge_to_something_outside_the_projection_is_dropped(self) -> None:
        """Otherwise the grid would carry a dangling reference to a node it never shows."""
        nodes = [_node("FMD@1", "failure-mode")]
        edges = [_edge("FMD@1", "leads-to", "CSN@1")]

        _, projected_edges = fmea_matrix.project_store_graph(nodes, edges)

        assert projected_edges == []

    def test_an_empty_store_projects_to_nothing(self) -> None:
        assert fmea_matrix.project_store_graph([], []) == ([], [])
