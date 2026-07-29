from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.diagram_types._base import DiagramTypeBase
from src.diagram_types.activity.renderer import ActivityPumlRenderer
from src.domain.diagrams.diagram_entities_schema import derive_diagram_entities_schema
from src.domain.diagrams.diagram_ontology_loader import DiagramOntology, load_diagram_ontology
from src.domain.modules.bridges import BridgeDeclaration
from src.domain.modules.module_types import ConnectionTypeName, DiagramTypeName, EntityTypeName, FreeOntology
from src.domain.ontology_representation.ontology_protocol import (
    DiagramRenderer,
    DiagramTypeModule,
    DiagramTypeWriteGuidance,
    diagram_type_ui_config_from_mapping,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

_OWN_ENTITY_TYPES: dict[EntityTypeName, EntityTypeInfo] = {}


def _load_config(package_dir: Path) -> dict[str, Any]:
    config_path = package_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _parse_element_classes(config: dict[str, Any]) -> dict[str, ElementClassInfo]:
    raw: object = config.get("element_classes") or {}
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(name): ElementClassInfo(
            name=str(name),
            description=str((info or {}).get("description") or "") if isinstance(info, Mapping) else "",
        )
        for name, info in raw.items()
    }


def _merge_ontology_into_config(
    config: dict[str, Any],
    ontology: DiagramOntology,
) -> dict[str, Any]:
    """Merge ontology entity type specs into config diagram_only_types.

    Copies all ontological fields (element_classes, required_connections, min, max,
    create_when, never_create_when, permitted_mappings, mapping_required) from ontology
    into existing config entries, and adds stub UI entries for ontology types not in config.
    """
    ui: dict[str, Any] = dict(config.get("ui") or {})
    dot: list[Any] = list(ui.get("diagram_only_types") or [])
    updated: list[dict[str, Any]] = []
    seen_types: set[str] = set()

    for entry in dot:
        if not isinstance(entry, Mapping):
            updated.append(entry)
            continue
        etype = str(entry.get("entity_type") or "")
        seen_types.add(etype)
        ont_et = ontology.entity_types.get(EntityTypeName(etype))
        merged: dict[str, Any] = dict(entry)
        if ont_et is not None:
            _apply_ontology_fields(merged, ont_et, ontology)
        updated.append(merged)

    # Add ontology-only entity types (e.g. annotation types like "note")
    for etype_name, ont_et in ontology.entity_types.items():
        if str(etype_name) in seen_types:
            continue
        stub: dict[str, Any] = {
            "entity_type": str(etype_name),
            "label": str(etype_name).title(),
        }
        _apply_ontology_fields(stub, ont_et, ontology)
        updated.append(stub)

    merged_ui = {**ui, "diagram_only_types": updated}
    return {**config, "ui": merged_ui}


def _apply_ontology_fields(
    entry: dict[str, Any],
    ont_et: EntityTypeInfo,
    ontology: DiagramOntology,
) -> None:
    """Copy all ontological fields from EntityTypeInfo into a config entry dict."""
    entry["classes"] = list(ont_et.classes)
    entry["create_when"] = ont_et.create_when
    entry["never_create_when"] = ont_et.never_create_when
    entry["min"] = ont_et.min
    entry["max"] = ont_et.max
    entry["mapping_required"] = ont_et.mapping_required
    pm = ont_et.permitted_mappings
    if pm.has_any():
        mapping_entry: dict[str, Any] = {
            "entity_types": list(pm.entity_types),
            "entity_classes": list(pm.entity_classes),
        }
        if pm.sources:
            mapping_entry["sources"] = [
                {
                    "ontology": source.ontology,
                    "entity_type": source.entity_type,
                    "entity_class": source.entity_class,
                    "transparent": source.transparent,
                }
                for source in pm.sources
            ]
        entry["permitted_mappings"] = mapping_entry
    raw_props = ontology.entity_type_properties.get(str(ont_et.artifact_type))
    if raw_props:
        entry["properties"] = raw_props
    raw_mf = ontology.entity_type_managed_fields.get(str(ont_et.artifact_type))
    if raw_mf:
        entry["managed_fields"] = raw_mf
    if ont_et.required_connections:
        entry["required_connections"] = [
            {
                "connection_type": rc.connection_type,
                "target": rc.target,
                "cardinality": [rc.cardinality_min, rc.cardinality_max],
            }
            for rc in ont_et.required_connections
        ]


class _ActivityDiagramType(DiagramTypeBase):
    def __init__(self, config: dict[str, Any], ontology: DiagramOntology) -> None:
        self._ontology = ontology
        merged_config = _merge_ontology_into_config(config, ontology)
        self._config = merged_config
        self._name = DiagramTypeName(str(config["name"]))
        self._element_classes = _parse_element_classes(config)
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

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        g: dict[str, Any] = self._config.get("guidance") or {}
        own_types = self._ui_config.diagram_only_types
        ab = self._ontology.allowed_bindings
        return DiagramTypeWriteGuidance(
            when_to_use=str(g.get("when_to_use") or ""),
            when_not_to_use=str(g.get("when_not_to_use") or ""),
            diagram_entities_schema=derive_diagram_entities_schema(own_types),
            own_entity_types=own_types,
            allowed_bindings=ab if not ab.is_empty() else None,
        )


_PACKAGE_DIR = Path(__file__).parent
_config = _load_config(_PACKAGE_DIR)
_ontology = load_diagram_ontology(_PACKAGE_DIR / "ontology.yaml")
module: DiagramTypeModule = _ActivityDiagramType(_config, _ontology)
