"""Private loader: YAML → _ArchiMate4Module instance."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

import yaml  # type: ignore[import-untyped]

from src.domain.guidance.guidance import GuidanceOverlay
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.behavioral_elements import BehavioralElementDeclaration
from src.domain.ontology_representation.classification_levels import (
    DERIVED_DEFAULT_LEVELS,
    ClassificationLevel,
    classification_levels_from_config,
)
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.ontology_representation.profile_registry import ProfileRegistry
from src.domain.ontology_representation.specializations import (
    SpecializationCatalog,
    merge_specialization_catalogs,
    overlay_specialization_guidance,
)
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet
from src.domain.relationships.relationship_derivation_restrictions import DerivationRestriction
from src.domain.relationships.relationship_derivation_rules import (
    CompositionRule,
    load_composition_rules,
    load_derivation_restrictions,
)
from src.ontologies.archimate_4._yaml_data import META_ONTOLOGY_ALIAS as META_ONTOLOGY_ALIAS
from src.ontologies.archimate_4._yaml_data import (
    build_permitted_relationships,
    load_connection_types,
    load_element_classes,
    load_entity_types,
    load_module_profiles,
    load_module_specializations,
)

_PACKAGE_DIR = Path(__file__).parent

_GLYPHS_PATH = _PACKAGE_DIR.parent.parent.parent / "tools" / "gui" / "src" / "ui" / "lib" / "archimateGlyphs.json"

DISPLAY_SECTION_ID = "archimate"


def _sprite_key(artifact_type: str) -> str:
    return artifact_type.replace("-", "_")


def _load_glyphs() -> dict[str, Any]:
    try:
        return cast(dict[str, Any], json.loads(_GLYPHS_PATH.read_text(encoding="utf-8")))
    except OSError:
        return {}


class _ArchiMate4Module:
    name = "archimate-4-0"
    display_section_id = DISPLAY_SECTION_ID
    module_class: Literal["architecture", "assurance"] = "architecture"
    enabled: bool = True
    requires: list[str] = []

    def __init__(
        self,
        entity_types: dict[EntityTypeName, EntityTypeInfo],
        connection_types: dict[ConnectionTypeName, ConnectionTypeInfo],
        permitted_relationships: PermittedRelationshipSet,
        matrix_abbreviations: dict[str, str],
        element_classes: dict[str, ElementClassInfo] | None = None,
        behavioral_elements: BehavioralElementDeclaration | None = None,
        specialization_catalog: SpecializationCatalog | None = None,
        profile_registry: ProfileRegistry | None = None,
        derivation_rules: tuple[CompositionRule, ...] = (),
        derivation_restrictions: tuple[DerivationRestriction, ...] = (),
        svg_converter: Callable[[str], str] | None = None,
        domain_order: tuple[str, ...] = (),
        classification_levels: tuple[ClassificationLevel, ...] = DERIVED_DEFAULT_LEVELS,
    ) -> None:
        self._classification_levels = classification_levels
        self._declared_domain_order = domain_order
        self._entity_types = entity_types
        self._connection_types = connection_types
        self._permitted_relationships = permitted_relationships
        self._matrix_abbreviations = matrix_abbreviations
        self._element_classes: dict[str, ElementClassInfo] = element_classes or {}
        self._behavioral_elements = behavioral_elements or BehavioralElementDeclaration()
        self._specialization_catalog = specialization_catalog or SpecializationCatalog.empty()
        self._profile_registry = profile_registry or ProfileRegistry.empty()
        self._svg_converter = svg_converter
        self._derivation_rules = derivation_rules
        self._derivation_restrictions = derivation_restrictions

        self._class_index: dict[ElementClassName, frozenset[EntityTypeName]] = {}
        _class_build: dict[ElementClassName, set[EntityTypeName]] = {}
        for ename, info in entity_types.items():
            for cls in info.classes:
                _class_build.setdefault(ElementClassName(cls), set()).add(ename)
        self._class_index = {k: frozenset(v) for k, v in _class_build.items()}

        self._classification_index: dict[str, frozenset[ConnectionTypeName]] = {}
        _clf_build: dict[str, set[ConnectionTypeName]] = {}
        for cname, info in connection_types.items():
            for clf in info.classes:
                _clf_build.setdefault(clf, set()).add(cname)
        self._classification_index = {k: frozenset(v) for k, v in _clf_build.items()}

        self._glyphs: dict[str, Any] = {}
        self._glyphs_loaded = False

    def _ensure_glyphs(self) -> None:
        if not self._glyphs_loaded:
            self._glyphs = _load_glyphs()
            self._glyphs_loaded = True

    @property
    def entity_types(self) -> dict[EntityTypeName, EntityTypeInfo]:
        return self._entity_types

    @property
    def domain_order(self) -> tuple[str, ...]:
        return self._declared_domain_order

    @property
    def connection_types(self) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
        return self._connection_types

    @property
    def permitted_relationships(self) -> PermittedRelationshipSet:
        return self._permitted_relationships

    @property
    def matrix_abbreviations(self) -> dict[str, str]:
        return self._matrix_abbreviations

    @property
    def element_classes(self) -> dict[str, ElementClassInfo]:
        return self._element_classes

    @property
    def behavioral_elements(self) -> BehavioralElementDeclaration:
        return self._behavioral_elements

    @property
    def classification_levels(self) -> tuple[ClassificationLevel, ...]:
        """The levels this ontology classifies an element through, declared in `entities.yaml`.

        Declared rather than derived, so the two-tier verification the scratchpad needs — refusal at
        the level relationships are keyed on, a warning at the level that only narrows them — is a
        consequence of what the ontology says about itself rather than a rule in each consumer.
        """
        return self._classification_levels

    @property
    def specialization_catalog(self) -> SpecializationCatalog:
        return self._specialization_catalog

    @property
    def profile_registry(self) -> ProfileRegistry:
        return self._profile_registry

    @property
    def derivation_rules(self) -> tuple[CompositionRule, ...]:
        return self._derivation_rules

    @property
    def derivation_restrictions(self) -> tuple[DerivationRestriction, ...]:
        return self._derivation_restrictions

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        return self._class_index.get(ElementClassName(cls), frozenset())

    def connection_types_with_class(self, cls: str) -> frozenset[ConnectionTypeName]:
        return self._classification_index.get(cls, frozenset())

    def permits_connection(
        self,
        src: EntityTypeName,
        tgt: EntityTypeName,
        conn: ConnectionTypeName,
    ) -> bool:
        return self._permitted_relationships.permits(src, tgt, conn)

    def render_display_section(
        self,
        artifact_type: str,
        name: str,
        alias: str,
    ) -> str:
        label = name.replace('"', "'")
        return f"label: {label}\nalias: {alias}"

    def extract_display_section(self, section_content: str) -> dict | None:
        text = re.sub(r"^```(?:yaml)?\n", "", section_content.strip(), count=1)
        text = re.sub(r"\n```$", "", text, count=1)
        try:
            loaded: Any = yaml.safe_load(text) or {}
        except Exception:  # noqa: BLE001
            return None
        return loaded if isinstance(loaded, dict) else None

    def sprite_for(self, artifact_type: str) -> str | None:
        self._ensure_glyphs()
        if not self._glyphs:
            return None
        kind = self._glyphs.get("types", {}).get(artifact_type)
        if not kind:
            return None
        markup = self._glyphs.get("kinds", {}).get(kind)
        if not markup:
            return None
        if self._svg_converter is None:
            return None
        key = _sprite_key(artifact_type)
        return f"sprite $archimate_{key} {self._svg_converter(markup)}"


def _specialization_guidance_entries(
    guidance: GuidanceOverlay,
) -> dict[tuple[str, Literal["entity", "connection"], str, str], tuple[str, str]]:
    entries: dict[tuple[str, Literal["entity", "connection"], str, str], tuple[str, str]] = {}
    for key, value in guidance.entries.items():
        if key.module_alias == META_ONTOLOGY_ALIAS and key.specialization:
            entries[(key.module_alias, key.concept_kind, key.type_name, key.specialization)] = (
                value.create_when,
                value.never_create_when,
            )
    return entries


def _validate_specialization_parents(
    catalog: SpecializationCatalog,
    entity_types: dict[EntityTypeName, EntityTypeInfo],
    connection_types: dict[ConnectionTypeName, ConnectionTypeInfo],
) -> None:
    for entry in catalog.entries:
        if entry.concept_kind == "entity" and EntityTypeName(entry.parent_type) not in entity_types:
            raise ValueError(f"Unknown parent entity type {entry.parent_type!r} for specialization {entry.slug!r}")
        if entry.concept_kind == "connection" and ConnectionTypeName(entry.parent_type) not in connection_types:
            raise ValueError(f"Unknown parent connection type {entry.parent_type!r} for specialization {entry.slug!r}")


def load_archimate_4_module(
    package_dir: Path,
    *,
    svg_converter: Callable[[str], str] | None = None,
    guidance: GuidanceOverlay | None = None,
    specializations: SpecializationCatalog | None = None,
) -> _ArchiMate4Module:
    with open(package_dir / "entities.yaml") as fh:
        entity_data = yaml.safe_load(fh)
    with open(package_dir / "connections.yaml") as fh:
        conn_data = yaml.safe_load(fh)

    entity_types = load_entity_types(entity_data, guidance)
    connection_types = load_connection_types(conn_data, guidance)
    derivation_rules = load_composition_rules(package_dir)
    derivation_restrictions = load_derivation_restrictions(package_dir)
    permitted = build_permitted_relationships(conn_data, entity_types)
    matrix_abbreviations: dict[str, str] = dict(conn_data.get("matrix_abbreviations", {}))
    element_classes = load_element_classes(entity_data)
    behavioral_elements = BehavioralElementDeclaration.from_mapping(entity_data)
    overlay = guidance if guidance is not None else GuidanceOverlay()
    module_specializations = overlay_specialization_guidance(
        load_module_specializations(package_dir, META_ONTOLOGY_ALIAS),
        _specialization_guidance_entries(overlay),
    )
    specialization_catalog = merge_specialization_catalogs(
        module_specializations,
        specializations or SpecializationCatalog.empty(),
    )
    _validate_specialization_parents(specialization_catalog, entity_types, connection_types)

    return _ArchiMate4Module(
        entity_types=entity_types,
        connection_types=connection_types,
        permitted_relationships=permitted,
        matrix_abbreviations=matrix_abbreviations,
        element_classes=element_classes,
        behavioral_elements=behavioral_elements,
        specialization_catalog=specialization_catalog,
        profile_registry=load_module_profiles(package_dir),
        derivation_rules=derivation_rules,
        derivation_restrictions=derivation_restrictions,
        svg_converter=svg_converter,
        domain_order=tuple(str(d) for d in entity_data.get("domain_order", ())),
        classification_levels=classification_levels_from_config(entity_data, module="archimate-4-0"),
    )
