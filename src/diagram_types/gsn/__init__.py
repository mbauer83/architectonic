"""GSN (Goal Structuring Notation) diagram type for assurance cases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.diagram_types._base import DiagramTypeBase
from src.diagram_types.gsn.renderer import GsnDiagramRenderer
from src.domain.modules.module_types import ConnectionTypeName, DiagramTypeName, EntityTypeName, FreeOntology
from src.domain.ontology_representation.ontology_protocol import (
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet
from src.domain.yaml_documents import parse_yaml

_EMPTY_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}
_EMPTY_CONNECTION_TYPES: dict[ConnectionTypeName, ConnectionTypeInfo] = {}

class _GsnDiagramType(DiagramTypeBase):
    module_class = "architecture"
    requires: list[str] = []

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

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
    def renderer(self) -> GsnDiagramRenderer:
        return GsnDiagramRenderer()

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        return DiagramTypeWriteGuidance(
            when_to_use=(
                "Use to render a Goal Structuring Notation (GSN) argument structure for an assurance case. "
                "Shows goals (G), strategies (S), solutions/evidence (Sn), contexts (C), "
                "assumptions (A), justifications (J), and undeveloped markers with supported-by "
                "and in-context-of edges, using GSN Community Standard notation. "
                "Use it directly for general architecture arguments, or publish a TLP-classified "
                "draft through the assurance GSN bridge."
            ),
            when_not_to_use=(
                "Do not use for bowtie threat models (use bowtie instead) or STPA control structures "
                "(use control-structure instead). GSN is for structured argumentation, not causal modelling."
            ),
            puml_notes=(
                "The payload is two flat arrays under `diagram_entities`: `nodes` and `edges`. A node"
                " is {node_id, name, gsn_type}, where gsn_type is one of goal, strategy, solution,"
                " context, assumption, justification, undeveloped; anything else is drawn as a goal.",
                "An edge is {source_id, target_id, conn_type} — note `source_id`/`target_id`, not the"
                " `source`/`target` the other diagram types use. conn_type is `supported-by` or"
                " `in-context-of`; anything else is drawn as supported-by rather than refused.",
                "Direction is parent → child: a goal is the SOURCE of the supported-by edge reaching"
                " the strategy or solution beneath it. Drawing it the other way inverts the argument"
                " and still renders, because the depth of every node is computed from these edges.",
                "`in-context-of` is what moves a node to the side rather than below: a context,"
                " assumption or justification reached that way sits beside the node it qualifies, at"
                " the same rank. Attaching one with supported-by instead puts it in the argument"
                " chain, claiming it is evidence.",
                "A claim that is deliberately not argued further gets an `undeveloped` node beneath"
                " it — the diamond — rather than being left as a leaf, which reads as an oversight.",
                "Labels are wrapped for you at a fixed column (narrower for a solution, which is a"
                " circle), so a long claim costs height rather than width. Node names still read"
                " best as one stated claim.",
                "Minimal example — one goal, one strategy, one solution, one context:\n"
                "  diagram_entities: {nodes: [\n"
                "      {node_id: g1, name: 'The store is confidential', gsn_type: goal},\n"
                "      {node_id: s1, name: 'Argue over each access path', gsn_type: strategy},\n"
                "      {node_id: sn1, name: 'Penetration test report', gsn_type: solution},\n"
                "      {node_id: c1, name: 'Store at rest', gsn_type: context}],\n"
                "    edges: [\n"
                "      {source_id: g1, target_id: s1, conn_type: supported-by},\n"
                "      {source_id: s1, target_id: sn1, conn_type: supported-by},\n"
                "      {source_id: g1, target_id: c1, conn_type: in-context-of}]}",
            ),
        )


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return parse_yaml(handle) or {}


module: DiagramTypeModule = _GsnDiagramType(_load_config(Path(__file__).parent))
