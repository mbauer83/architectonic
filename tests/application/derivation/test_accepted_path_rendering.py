"""Resolving a persisted diagram's accepted witness paths into renderable connections,
proven end-to-end against the actual renderer: a layered fixture (technology node →
service → business process, service layer omitted from the rendered entities) renders
the derived serving connection with serving notation and a derived marker."""

from __future__ import annotations

from pathlib import Path

from src.application.derivation.accepted_path_rendering import resolve_accepted_derived_connections
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.view_derivations import DerivationSelection
from src.infrastructure.rendering.generic_puml_renderer import GenericPumlRenderer
from tests.fixtures.viewpoints.derivation_examples import ExampleGraph, catalog, connection, entity

_CATALOG = catalog()
_ARCHIMATE_CONFIG: dict[str, object] = {
    "includes": [], "grouping": {"stereotype_pattern": "{hierarchy_0|capitalize}Grouping"},
}


def _renderable_entity(artifact_id: str, artifact_type: str, alias: str) -> EntityRecord:
    """A renderer-ready entity: ``derivation_examples.entity()`` builds a bare record for
    pure relationship-derivation tests, with no ArchiMate display block, so it never
    renders on a diagram."""
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=alias,
        version="1",
        status="draft",
        domain="",
        subdomain="",
        path=Path("/examples"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={"archimate": f'```yaml\nlabel: "{alias}"\nalias: {alias}\n```'},
        display_label=alias,
        display_alias=alias,
    )


def _layered_graph() -> ExampleGraph:
    return ExampleGraph(
        entities={
            "node": entity("node", "technology-node"),
            "svc": entity("svc", "service"),
            "proc": entity("proc", "process"),
        },
        connections=[
            connection("c1", "node", "svc", "archimate-serving"),
            connection("c2", "svc", "proc", "archimate-serving"),
        ],
    )


_PATH_KEY = "c1@fwd|c2@fwd"


class TestResolveAcceptedDerivedConnections:
    def test_no_selection_resolves_nothing(self) -> None:
        assert resolve_accepted_derived_connections(None, read_access=_layered_graph(), catalog=_CATALOG) == []

    def test_accepted_path_resolves_to_a_synthetic_record(self) -> None:
        selection = DerivationSelection(included_paths=(_PATH_KEY,))
        records = resolve_accepted_derived_connections(selection, read_access=_layered_graph(), catalog=_CATALOG)
        assert len(records) == 1
        record = records[0]
        assert record.source == "node"
        assert record.target == "proc"
        assert record.conn_type == "archimate-serving"
        assert record.artifact_id == f"derived::archimate-serving::{_PATH_KEY}"

    def test_broken_path_resolves_to_nothing(self) -> None:
        graph = _layered_graph()
        graph.connections = [c for c in graph.connections if c.artifact_id != "c1"]
        selection = DerivationSelection(included_paths=(_PATH_KEY,))
        assert resolve_accepted_derived_connections(selection, read_access=graph, catalog=_CATALOG) == []


class TestLayeredFixtureRendersInBothContexts:
    def test_derived_connection_renders_with_serving_notation_and_derived_marker(self, tmp_path: Path) -> None:
        graph = _layered_graph()
        selection = DerivationSelection(included_paths=(_PATH_KEY,))
        derived_records = resolve_accepted_derived_connections(selection, read_access=graph, catalog=_CATALOG)
        assert len(derived_records) == 1

        node_entity = _renderable_entity("node", "technology-node", "NODE_A")
        process_entity = _renderable_entity("proc", "process", "PROC_A")
        renderer = GenericPumlRenderer(_ARCHIMATE_CONFIG)
        puml = renderer.render_body(
            "Layered", [node_entity, process_entity], derived_records, "archimate-layered", tmp_path,
        )

        conn_lines = [ln for ln in puml.splitlines() if "NODE_A" in ln and "PROC_A" in ln]
        assert any("NODE_A -[dotted]up-> PROC_A" in ln for ln in conn_lines)  # domain-rank hint composes with the style
        # serving's arrowhead (open '>', not the hollow '|>' triangle) survives the
        # line-style insertion, and [dotted] marks it derived-and-potential.
