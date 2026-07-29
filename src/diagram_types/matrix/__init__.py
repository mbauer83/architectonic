from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.diagram_types._base import DiagramTypeBase
from src.domain.concept_scope import ConceptScope
from src.domain.modules.module_types import ConnectionTypeName, DiagramTypeName, EntityTypeName, FreeOntology
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import (
    DiagramRenderer,
    DiagramRendererReferences,
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

_EMPTY_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}
_EMPTY_CONNECTION_TYPES: dict[ConnectionTypeName, ConnectionTypeInfo] = {}


class _MatrixRenderer:
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
        del name, entities, connections, diagram_type, repo_root, diagram_entities, diagram_connections
        raise ValueError("Matrix diagrams use the markdown matrix renderer")

    def inject_includes(self, body: str, repo_root: Path) -> str:
        del repo_root
        return body

    def collect_references(
        self,
        diagram_type: str,
        repo_root: Path,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
        bindings: list[dict[str, object]] | None = None,
    ) -> DiagramRendererReferences:
        del diagram_type, repo_root, diagram_entities, diagram_connections, bindings
        return DiagramRendererReferences()



class _MatrixDiagramType(DiagramTypeBase):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    @property
    def name(self) -> DiagramTypeName:
        return DiagramTypeName(str(self._config["name"]))

    @property
    def primary_ontology(self):  # type: ignore[override]
        return FreeOntology

    def concept_scope(self, registry: object | None = None) -> ConceptScope:
        del registry
        return ConceptScope.unrestricted()

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
        return _MatrixRenderer()

    def read_diagram_extras(self, parsed_source: dict[str, Any]) -> dict[str, Any]:
        return {"matrix_body": str(parsed_source.get("puml_body") or "").strip()}

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        return DiagramTypeWriteGuidance(
            when_to_use=(
                "Use when you need to visualize relationships between two sets of entities as a grid. "
                "Good for CRUD matrices, responsibility matrices, or any N×M relationship overview."
            ),
            when_not_to_use=(
                "Do not use for process flows, structural hierarchy, or diagrams where visual layout "
                "matters. Matrices work best for homogeneous relationship sets, not mixed-type graphs."
            ),
            accepted_domains=("all",),
        )


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


module: DiagramTypeModule = _MatrixDiagramType(_load_config(Path(__file__).parent))
