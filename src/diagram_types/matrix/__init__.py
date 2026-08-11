from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.diagram_types._base import DiagramTypeBase
from src.domain.concept_scope import ConceptScope
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
            puml_notes=(
                "There is no PUML body. A matrix is a markdown table, authored with"
                " `artifact_create_matrix(name=…, matrix_markdown=…)` and edited with"
                " `artifact_edit_diagram`, which accepts only name/keywords/version/status/tlp/group"
                " here and preserves the table. Passing `puml` to either is refused, and calling the"
                " renderer raises — so a matrix authored like the other diagram types fails at the"
                " tool boundary rather than rendering wrongly.",
                "`matrix_markdown` is an ordinary GitHub-flavoured table: the first row names the"
                " columns, the first column names the rows, and each cell holds whatever the matrix"
                " asserts about that pair — a role letter (CRUD, RACI), a mark, or a short phrase.",
                "Entity ids written into cells or headers are linked back to the model by default"
                " (`infer_entity_ids`, `auto_link_entity_ids`), which is what makes a matrix"
                " traceable rather than a picture of a table. Naming the entities by id rather than"
                " by prose is therefore the difference between a matrix that participates in the"
                " model and one that only looks like it does.",
            ),
        )


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return parse_yaml(handle) or {}


module: DiagramTypeModule = _MatrixDiagramType(_load_config(Path(__file__).parent))
