from __future__ import annotations

from pathlib import Path
from typing import Any

from src.diagram_types._base import DiagramTypeBase
from src.diagram_types.datatype.renderer import DatatypePumlRenderer
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
        return parse_yaml(handle) or {}


class _DatatypeDiagramType(DiagramTypeBase):
    def __init__(self, config: dict[str, Any], ontology: DiagramOntology) -> None:
        self._ontology = ontology
        merged_config = merge_ontology_into_diagram_only_types(config, ontology)
        self._config = merged_config
        self._name = DiagramTypeName(str(config["name"]))
        self._element_classes = element_classes_from_config(config)
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
            puml_notes=puml_notes_from_config(self._config),
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
