from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.diagram_types._base import DiagramTypeBase
from src.diagram_types.datatype.renderer import DatatypePumlRenderer
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


def _build_classifier_label_map(
    diagram_entities: dict[str, Any],
    candidate: Any,
) -> dict[str, str]:
    """Return id→label for all visible classifiers.

    Inline classifiers (defined in *diagram_entities*) take precedence so that
    the same-write contract works without a candidate.
    """
    label_map: dict[str, str] = {}

    if candidate is not None:
        for entity in candidate.list_entities(artifact_type="classifier"):
            label_map[entity.artifact_id] = entity.name

    for clf in diagram_entities.get("classifier") or []:
        if isinstance(clf, dict):
            clf_id = str(clf.get("id") or "")
            if clf_id:
                label_map[clf_id] = str(clf.get("label") or clf_id)

    return label_map


def _resolve_one_type_label(
    type_ref: Any,
    label_map: dict[str, str],
    primitive_names: frozenset[str],
) -> Any:
    """Resolve a single attribute type ref to a label string or return the original."""
    if not isinstance(type_ref, dict):
        return type_ref
    kind = type_ref.get("kind")
    if kind == "primitive":
        return str(type_ref.get("name") or "")
    if kind == "classifier":
        clf_id = str(type_ref.get("id") or "")
        return label_map.get(clf_id, clf_id)
    return type_ref


def _prepare_classifier_for_render(
    clf: Any,
    label_map: dict[str, str],
    primitive_names: frozenset[str],
) -> Any:
    if not isinstance(clf, dict):
        return clf
    new_attrs = [
        {**attr, "type": _resolve_one_type_label(attr.get("type"), label_map, primitive_names)}
        if isinstance(attr, dict) and isinstance(attr.get("type"), dict)
        else attr
        for attr in (clf.get("attributes") or [])
    ]
    return {**clf, "attributes": new_attrs}


def _apply_type_labels(
    diagram_entities: dict[str, Any],
    label_map: dict[str, str],
    primitive_names: frozenset[str],
) -> dict[str, Any]:
    prepared = [
        _prepare_classifier_for_render(clf, label_map, primitive_names)
        for clf in (diagram_entities.get("classifier") or [])
    ]
    return {**diagram_entities, "classifier": prepared}


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
    entry["identity_scope"] = ont_et.identity_scope
    if ont_et.id_prefix is not None:
        entry["id_prefix"] = ont_et.id_prefix


class _DatatypeDiagramType(DiagramTypeBase):
    def __init__(self, config: dict[str, Any], ontology: DiagramOntology) -> None:
        self._ontology = ontology
        merged_config = _merge_ontology_into_config(config, ontology)
        self._config = merged_config
        self._name = DiagramTypeName(str(config["name"]))
        self._element_classes = _parse_element_classes(config)
        self._ui_config = diagram_type_ui_config_from_mapping(
            merged_config,
            default_label="Datatype Diagram",
        )
        self._renderer = DatatypePumlRenderer(config)

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
    def diagram_entity_type_infos(self) -> dict[EntityTypeName, EntityTypeInfo]:
        """EntityTypeInfo for diagram-owned entity types (authoritative source for identity metadata)."""
        return dict(self._ontology.entity_types)

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

    def prepare_render_model(
        self, diagram_entities: dict[str, Any], candidate: Any = None
    ) -> dict[str, Any]:
        """Resolve attribute type refs to label strings suitable for PUML rendering.

        Builds a label map from (1) classifiers defined inline in *diagram_entities*,
        then (2) any entities in *candidate*.  Converts {kind:…} type dicts to plain
        strings; non-dict types are preserved as-is (supports legacy string types).
        """
        label_map = _build_classifier_label_map(diagram_entities, candidate)
        primitive_names = frozenset(
            str(p) for p in (self._config.get("ui") or {}).get("primitive_types") or []
        )
        return _apply_type_labels(diagram_entities, label_map, primitive_names)

    def repository_verification_contributions(self) -> tuple:
        from src.diagram_types.datatype._contributions import _ReferenceImpactContribution  # noqa: PLC0415

        return (_ReferenceImpactContribution(),)

    def diagram_verification_contributions(self) -> tuple:
        from src.diagram_types.datatype._contributions import (  # noqa: PLC0415
            ATTRIBUTE_TYPE_SCHEMA_CONTRIBUTION,
            BACKING_CONSISTENCY_CONTRIBUTION,
            _ProjectionBasedContributions,
        )
        from src.diagram_types.datatype._contributions_keys import (  # noqa: PLC0415
            GENERALIZATION_SET_CONTRIBUTION,
            KEY_CONSTRAINT_CONTRIBUTION,
        )
        primitive_names = frozenset(
            str(p) for p in (self._config.get("ui") or {}).get("primitive_types") or []
        )
        return (
            BACKING_CONSISTENCY_CONTRIBUTION,
            ATTRIBUTE_TYPE_SCHEMA_CONTRIBUTION,
            KEY_CONSTRAINT_CONTRIBUTION,
            GENERALIZATION_SET_CONTRIBUTION,
            _ProjectionBasedContributions(primitive_names),
        )


_PACKAGE_DIR = Path(__file__).parent
_config = _load_config(_PACKAGE_DIR)
_ontology = load_diagram_ontology(_PACKAGE_DIR / "ontology.yaml")
module: DiagramTypeModule = _DatatypeDiagramType(_config, _ontology)
