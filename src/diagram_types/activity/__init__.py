from __future__ import annotations

from pathlib import Path
from typing import Any

from src.diagram_types._base import DiagramTypeBase
from src.diagram_types.activity.renderer import ActivityPumlRenderer
from src.domain.diagrams.diagram_entities_schema import derive_diagram_entities_schema
from src.domain.diagrams.diagram_ontology_loader import DiagramOntology, load_diagram_ontology
from src.domain.diagrams.diagram_ontology_merge import merge_ontology_into_diagram_only_types
from src.domain.diagrams.diagram_type_config import puml_notes_from_config
from src.domain.modules.bridges import BridgeDeclaration
from src.domain.modules.module_types import ConnectionTypeName, DiagramTypeName, EntityTypeName, FreeOntology
from src.domain.ontology_representation.ontology_protocol import (
    DiagramRenderer,
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
    diagram_type_ui_config_from_mapping,
    element_classes_from_config,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet
from src.domain.yaml_documents import parse_yaml

_OWN_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return parse_yaml(handle) or {}


class _ActivityDiagramType(DiagramTypeBase):
    def __init__(self, config: dict[str, Any], ontology: DiagramOntology) -> None:
        self._ontology = ontology
        merged_config = merge_ontology_into_diagram_only_types(config, ontology)
        self._config = merged_config
        self._name = DiagramTypeName(str(config["name"]))
        self._element_classes = element_classes_from_config(config)
        self._ui_config = diagram_type_ui_config_from_mapping(
            merged_config,
            default_label="Activity Diagram",
        )
        self._renderer = ActivityPumlRenderer(config)

    @property
    def element_classes(self) -> dict[str, ElementClassInfo]:
        return self._element_classes

    @property
    def name(self) -> DiagramTypeName:
        return self._name

    @property
    def primary_ontology(self):  # type: ignore[override]
        return FreeOntology

    @property
    def own_entity_types(self) -> dict[EntityTypeName, EntityTypeInfo]:
        return _OWN_ENTITY_TYPES

    @property
    def own_connection_types(self) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
        return dict(self._ontology.connection_types)

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet:
        return self._ontology.permitted_relationships

    @property
    def bridges(self) -> tuple[BridgeDeclaration, ...]:
        return self._ontology.bridges

    @property
    def renderer(self) -> DiagramRenderer:
        return self._renderer

    def diagram_verification_contributions(self) -> tuple:
        from src.diagram_types.activity._contributions import STEP_COVERAGE_CONTRIBUTION  # noqa: PLC0415

        return (STEP_COVERAGE_CONTRIBUTION,)

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        g: dict[str, Any] = self._config.get("guidance") or {}
        own_types = self._ui_config.diagram_only_types
        ab = self._ontology.allowed_bindings
        return DiagramTypeWriteGuidance(
            when_to_use=str(g.get("when_to_use") or ""),
            when_not_to_use=str(g.get("when_not_to_use") or ""),
            diagram_entities_schema=derive_diagram_entities_schema(own_types),
            own_entity_types=own_types,
            puml_notes=puml_notes_from_config(self._config),
            allowed_bindings=ab if not ab.is_empty() else None,
        )


_PACKAGE_DIR = Path(__file__).parent
_config = _load_config(_PACKAGE_DIR)
_ontology = load_diagram_ontology(_PACKAGE_DIR / "ontology.yaml")
module: DiagramTypeModule = _ActivityDiagramType(_config, _ontology)
