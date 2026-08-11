"""Bowtie diagram type for threat/hazard barrier analysis.

Renders a PlantUML component diagram showing the bowtie structure:
  threat → [barrier_left] → top_event → [barrier_right] → consequence

diagram_entities JSON format:
  nodes: list of {node_id, name, node_type, role}
    role values: "threat", "top_event", "consequence", "barrier_left", "barrier_right"
  edges: list of {source_id, target_id, label}

module_class = "assurance"; requires the confidential store.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.diagram_types._assurance_analysis_scope import analysis_methods_from
from src.diagram_types._base import DiagramTypeBase
from src.diagram_types._store_graph_payload import nodes_and_edges_from
from src.diagram_types.bowtie import notation
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

class _BowtieDiagramRenderer:
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

    def inject_includes(self, body: str, repo_root: Path) -> str:
        del repo_root
        return body


class _BowtieDiagramType(DiagramTypeBase):
    module_class = "assurance"
    requires: list[str] = ["confidential_store"]

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def project_store_graph(
        self,
        nodes: Sequence[Mapping[str, object]],
        edges: Sequence[Mapping[str, object]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """The sub-graph a bowtie draws: nodes with a bowtie role, and the edges between them."""
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
        return _BowtieDiagramRenderer()

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        return DiagramTypeWriteGuidance(
            when_to_use=(
                "Use to visualise a bowtie risk model: threats on the left, a top event in the "
                "centre, consequences on the right, with barrier controls on each side. "
                "Suitable for safety, security, and operational risk communication."
            ),
            when_not_to_use=(
                "Do not use for STPA control-structure diagrams (use control-structure instead) "
                "or for GSN argument structures (use gsn instead). "
                "This diagram type is assurance-only and renders into the confidential store context."
            ),
            puml_notes=(
                "The payload is two flat arrays under `diagram_entities`: `nodes` and `edges`"
                " (`diagram_connections` is appended to the latter). A node is"
                " {node_id, name, node_type?, role?}; an edge is {source_id, target_id, conn_type}"
                " — `source_id`/`target_id`, not `source`/`target`.",
                "Where a node lands is its ROLE, and an authored `role` always wins: threat,"
                " barrier_left, top_event, barrier_right, consequence — left to right, in that order."
                " State it when authoring a diagram directly; the derivation below exists for content"
                " projected out of the assurance store.",
                "Derived roles come from `node_type`: unsafe-control-action and loss-scenario are"
                " threats, hazard is the top event, loss is a consequence, and assurance-constraint is"
                " a PREVENTIVE barrier — unless it is the source of a `mitigates` edge, which moves it"
                " to the consequence side. That one edge is the only thing distinguishing the two"
                " barrier columns, so a mitigating barrier without it renders on the wrong side.",
                "A node whose role is neither authored nor derivable is kept and drawn last, unstyled."
                " That is deliberate: an unplaced node in a bowtie is a modelling gap worth seeing,"
                " not something to drop quietly.",
                "One top event. The shape is named for a single hazard with pathways in and out;"
                " several top events render as several centres and stop reading as a bowtie.",
            ),
        )


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return parse_yaml(handle) or {}


module: DiagramTypeModule = _BowtieDiagramType(_load_config(Path(__file__).parent))
