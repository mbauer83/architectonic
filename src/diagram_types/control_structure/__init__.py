"""Control-structure diagram type for STPA/STAMP analysis.

Renders a PlantUML component diagram from diagram_entities JSON, showing
control-structure-nodes (CSN) and control-actions (CTA) with their
issues/acts-on/feedback edges.  Binding status is visualised via
background colour and a name marker.

module_class = "assurance"; requires the confidential store.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.diagram_types._assurance_analysis_scope import analysis_methods_from
from src.diagram_types._base import DiagramTypeBase
from src.diagram_types._store_graph_payload import nodes_and_edges_from
from src.diagram_types.control_structure import notation
from src.domain.modules.module_types import ConnectionTypeName, DiagramTypeName, EntityTypeName, FreeOntology
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import (
    DiagramRenderer,
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet
from src.domain.yaml_documents import parse_yaml

_EMPTY_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}
_EMPTY_CONNECTION_TYPES: dict[ConnectionTypeName, ConnectionTypeInfo] = {}

# binding_status → (PlantUML background colour, label suffix)
class _ControlStructureRenderer:
    def render_body(
        self,
        name: str,
        entities: Sequence[EntityRecord],
        connections: Sequence[ConnectionRecord],
        diagram_type: str,
        repo_root: Path,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
    ) -> str:
        del entities, connections, diagram_type, repo_root
        # Normalising the payload is this renderer's whole job; the drawing itself is shared with
        # the live store projection, so the two cannot disagree.
        nodes, edges = nodes_and_edges_from(diagram_entities, diagram_connections)
        return notation.render(nodes, edges, title=name)

    def node_representing_edges(
        self,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
    ) -> list[dict[str, str]]:
        """Which drawn arrows stand for a control action (see `NodeRepresentingEdgeRenderer`)."""
        nodes, edges = nodes_and_edges_from(diagram_entities, diagram_connections)
        return notation.node_representing_edges(nodes, edges)

    def inject_includes(self, body: str, repo_root: Path) -> str:
        del repo_root
        return body


class _ControlStructureDiagramType(DiagramTypeBase):
    module_class = "assurance"
    requires: list[str] = ["confidential_store"]

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def project_store_graph(
        self,
        nodes: Sequence[Mapping[str, object]],
        edges: Sequence[Mapping[str, object]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """The sub-graph a control structure draws: its structural nodes and control actions, with
        the edges between them."""
        return notation.project_store_graph(nodes, edges)

    @property
    def analysis_methods(self) -> frozenset[str]:
        return analysis_methods_from(self._config)

    @property
    def name(self) -> DiagramTypeName:
        return DiagramTypeName(str(self._config["name"]))

    @property
    def primary_ontology(self):  # type: ignore[override]
        return FreeOntology

    @property
    def own_entity_types(self) -> dict[EntityTypeName, EntityTypeInfo]:
        return _EMPTY_ENTITY_TYPES

    @property
    def own_connection_types(self) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
        return _EMPTY_CONNECTION_TYPES

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def renderer(self) -> DiagramRenderer:
        return _ControlStructureRenderer()

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        return DiagramTypeWriteGuidance(
            when_to_use=(
                "Use to visualise the STAMP control structure for an STPA analysis. "
                "Shows controllers, controlled processes, and control actions with their "
                "binding status relative to the architecture model."
            ),
            when_not_to_use=(
                "Do not use for general component architecture or deployment topology. "
                "This diagram type is assurance-only and renders into the confidential store context."
            ),
            puml_notes=(
                "The payload is two flat arrays under `diagram_entities`: `nodes` and `edges`"
                " (`diagram_connections` is appended to the latter). A node is"
                " {node_id, name, node_type, binding_status?, role?}, and node_type is either"
                " `control-structure-node` — a controller or a controlled process — or"
                " `control-action`. A node of any other type is not drawn.",
                "An edge is {source_id, target_id, conn_type} — `source_id`/`target_id`, not"
                " `source`/`target`. The loop is spelled out with four names:"
                " control-structure-node --issues--> control-action --acts-on--> control-structure-node,"
                " `acts-through` for an action routed via an actuator, and `feedback` between two"
                " control-structure nodes.",
                "The relation names carry the meaning; direction alone does not. Other relations also"
                " point at a control action (a UCA `concerns` one) and none of them is part of the"
                " loop, so an edge named anything else is drawn as a plain arrow and takes no part in"
                " collapsing the action onto it.",
                "A control action is drawn as the labelled ARROW between its endpoints wherever the"
                " loop allows, and as a box only where collapsing it would hide something. Authoring"
                " it as a box on purpose is therefore not available — express it through its"
                " `issues`/`acts-on` pair and let the renderer decide.",
                "Feedback is authored the way it flows, from the sensing node back to the controller,"
                " and renders dotted so the two halves of the loop read differently. Reversing it"
                " inverts the loop and still renders.",
                "`binding_status` is the modelling-gap signal, not decoration: `unbound-pending`"
                " marks the node yellow with a `[?]`, `out-of-scope` greys it with a `[~]`, and"
                " `bound` (the default) leaves the surface's own fill in place.",
            ),
        )


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return parse_yaml(handle) or {}


module: DiagramTypeModule = _ControlStructureDiagramType(_load_config(Path(__file__).parent))
