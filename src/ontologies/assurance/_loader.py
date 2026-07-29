"""Assurance ontology module loader: YAML → _AssuranceModule instance."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]

from src.domain.guidance.guidance import ConceptKind, GuidanceOverlay, resolved_type_guidance
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.behavioral_elements import BehavioralElementDeclaration
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.ontology_representation.profile_registry import ProfileRegistry
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.domain.relationships.permitted_relationships import (
    PermittedRelationship,
    PermittedRelationshipSet,
)
from src.domain.relationships.relationship_derivation_restrictions import DerivationRestriction
from src.domain.relationships.relationship_derivation_rules import (
    CompositionRule,
    load_composition_rules,
    load_derivation_restrictions,
)

DISPLAY_SECTION_ID = "assurance"

_PACKAGE_DIR = Path(__file__).parent
META_ONTOLOGY_ALIAS = "assurance"


class _AssuranceModule:
    name = "assurance"
    display_section_id = DISPLAY_SECTION_ID
    module_class: Literal["architecture", "assurance"] = "assurance"
    enabled: bool = True
    requires: list[str] = ["confidential_store"]
    specialization_catalog: SpecializationCatalog = SpecializationCatalog.empty()
    profile_registry: ProfileRegistry = ProfileRegistry.empty()

    def __init__(
        self,
        entity_types: dict[EntityTypeName, EntityTypeInfo],
        connection_types: dict[ConnectionTypeName, ConnectionTypeInfo],
        permitted_relationships: PermittedRelationshipSet,
        element_classes: dict[str, ElementClassInfo],
        derivation_rules: tuple[CompositionRule, ...] = (),
        derivation_restrictions: tuple[DerivationRestriction, ...] = (),
        reference_types: dict[str, str] | None = None,
    ) -> None:
        self._entity_types = entity_types
        self._connection_types = connection_types
        self._permitted_relationships = permitted_relationships
        self._element_classes = element_classes
        self._derivation_rules = derivation_rules
        self._derivation_restrictions = derivation_restrictions
        self._reference_types = dict(reference_types or {})

        self._class_index: dict[ElementClassName, frozenset[EntityTypeName]] = {}
        _cb: dict[ElementClassName, set[EntityTypeName]] = {}
        for ename, info in entity_types.items():
            for cls in info.classes:
                _cb.setdefault(ElementClassName(cls), set()).add(ename)
        self._class_index = {k: frozenset(v) for k, v in _cb.items()}

        self._clf_index: dict[str, frozenset[ConnectionTypeName]] = {}
        _cfb: dict[str, set[ConnectionTypeName]] = {}
        for cname, info in connection_types.items():
            for clf in info.classes:
                _cfb.setdefault(clf, set()).add(cname)
        self._clf_index = {k: frozenset(v) for k, v in _cfb.items()}

    @property
    def entity_types(self) -> dict[EntityTypeName, EntityTypeInfo]:
        return self._entity_types

    @property
    def connection_types(self) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
        return self._connection_types

    @property
    def permitted_relationships(self) -> PermittedRelationshipSet:
        return self._permitted_relationships

    @property
    def reference_types(self) -> dict[str, str]:
        """The arch_refs reference-type catalog (cross-module architecture
        references) — deliberately distinct from assurance edge types so a
        transport surface can never submit one through the other's mutation
        use case."""
        return dict(self._reference_types)

    @property
    def derivation_rules(self) -> tuple[CompositionRule, ...]:
        return self._derivation_rules

    @property
    def derivation_restrictions(self) -> tuple[DerivationRestriction, ...]:
        return self._derivation_restrictions

    @property
    def element_classes(self) -> dict[str, ElementClassInfo]:
        return self._element_classes

    @property
    def behavioral_elements(self) -> BehavioralElementDeclaration:
        """Empty: this ontology's types are not architecture elements, so none of them acts in the
        sense the declaration is about. Stated rather than inherited, so the answer is deliberate."""
        return BehavioralElementDeclaration()

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        return self._class_index.get(ElementClassName(cls), frozenset())

    def connection_types_with_class(self, cls: str) -> frozenset[ConnectionTypeName]:
        return self._clf_index.get(cls, frozenset())

    def permits_connection(
        self,
        src: EntityTypeName,
        tgt: EntityTypeName,
        conn: ConnectionTypeName,
    ) -> bool:
        return self._permitted_relationships.permits(src, tgt, conn)

    def render_display_section(self, artifact_type: str, name: str, alias: str) -> str:
        label = name.replace('"', "'")
        return f"label: {label}\nalias: {alias}"

    def extract_display_section(self, section_content: str) -> dict | None:
        import re

        text = re.sub(r"^```(?:yaml)?\n", "", section_content.strip(), count=1)
        text = re.sub(r"\n```$", "", text, count=1)
        try:
            loaded: Any = yaml.safe_load(text) or {}
        except Exception:  # noqa: BLE001
            return None
        return loaded if isinstance(loaded, dict) else None

    def sprite_for(self, artifact_type: str) -> str | None:
        return None


def _type_guidance(
    guidance: GuidanceOverlay, kind: ConceptKind, artifact_type: str, info: dict[str, Any]
) -> tuple[str, str]:
    return resolved_type_guidance(
        guidance,
        module_alias=META_ONTOLOGY_ALIAS,
        concept_kind=kind,
        type_name=artifact_type,
        declared=info,
    )


def _load_entity_types(
    data: dict[str, Any], guidance: GuidanceOverlay | None = None
) -> dict[EntityTypeName, EntityTypeInfo]:
    overlay = guidance if guidance is not None else GuidanceOverlay()
    out: dict[EntityTypeName, EntityTypeInfo] = {}
    for artifact_type, info in data.get("entity_types", {}).items():
        raw_hierarchy = info.get("hierarchy", [])
        hierarchy = tuple(raw_hierarchy) + (artifact_type,)
        create_when, never_create_when = _type_guidance(overlay, "entity", artifact_type, info)
        out[EntityTypeName(artifact_type)] = EntityTypeInfo(
            artifact_type=artifact_type,
            prefix=info["prefix"],
            hierarchy=hierarchy,
            classes=tuple(info.get("classes", ())),
            create_when=create_when,
            never_create_when=never_create_when,
            internal=bool(info.get("internal", False)),
        )
    return out


def _load_connection_types(
    data: dict[str, Any], guidance: GuidanceOverlay | None = None
) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
    overlay = guidance if guidance is not None else GuidanceOverlay()
    out: dict[ConnectionTypeName, ConnectionTypeInfo] = {}
    conn_name: str
    conn_entry: dict[str, Any]
    for _lang, types in data.get("connection_types", {}).items():
        for conn_name, conn_entry in (types or {}).items():
            raw: dict[str, Any] = conn_entry or {}
            hp_raw = raw.get("hierarchy_priority")
            create_when, never_create_when = _type_guidance(overlay, "connection", conn_name, raw)
            out[ConnectionTypeName(conn_name)] = ConnectionTypeInfo(
                artifact_type=conn_name,
                conn_lang="assurance",
                create_when=create_when,
                never_create_when=never_create_when,
                archimate_relationship_type=None,
                symmetric=bool(raw.get("symmetric", False)),
                puml_arrow=raw.get("puml_arrow", "-->"),
                show_stereotype=bool(raw.get("show_stereotype", "puml_arrow" not in raw)),
                classes=tuple(raw.get("classes", ())),
                hierarchy_priority=int(hp_raw) if hp_raw is not None else None,
                hierarchy_label=str(raw["hierarchy_label"]) if raw.get("hierarchy_label") else None,
                bidirectional_sync=bool(raw.get("bidirectional_sync", False)),
            )
    return out


def _load_element_classes(data: dict[str, Any]) -> dict[str, ElementClassInfo]:
    out: dict[str, ElementClassInfo] = {}
    class_name: str
    class_entry: Any
    for class_name, class_entry in (data.get("element_classes") or {}).items():
        raw: dict[str, Any] = class_entry or {}
        out[str(class_name)] = ElementClassInfo(
            name=str(class_name),
            description=str(raw.get("description") or ""),
        )
    return out


def _build_permitted_relationships(
    data: dict[str, Any],
    entity_types: dict[EntityTypeName, EntityTypeInfo],
) -> PermittedRelationshipSet:
    all_types = [str(k) for k in entity_types]
    class_members: dict[str, list[str]] = {}
    for ename, info in entity_types.items():
        for cls in info.classes:
            class_members.setdefault(cls, []).append(str(ename))

    rules: set[PermittedRelationship] = set()
    for rule in data.get("permitted_relationships", []):
        raw_src, raw_tgt, raw_conns = rule
        conn_types = [ConnectionTypeName(c) for c in raw_conns]

        def _expand(ref: object) -> list[str]:
            if isinstance(ref, list):
                result: list[str] = []
                for item in ref:
                    result.extend(_expand(item))
                return result
            ref_str = str(ref)
            if ref_str == "@all":
                return list(all_types)
            if ref_str.startswith("@"):
                return list(class_members.get(ref_str[1:], []))
            return [ref_str]

        for src in _expand(raw_src):
            for tgt in _expand(raw_tgt):
                for ct in conn_types:
                    rules.add(
                        PermittedRelationship(
                            source_type=EntityTypeName(src),
                            target_type=EntityTypeName(tgt),
                            connection_type=ct,
                        )
                    )
    return PermittedRelationshipSet(frozenset(rules))


def load_assurance_module(package_dir: Path, *, guidance: GuidanceOverlay | None = None) -> _AssuranceModule:
    with open(package_dir / "entities.yaml") as fh:
        entity_data = yaml.safe_load(fh)
    with open(package_dir / "connections.yaml") as fh:
        conn_data = yaml.safe_load(fh)

    entity_types = _load_entity_types(entity_data, guidance)
    connection_types = _load_connection_types(conn_data, guidance)
    permitted = _build_permitted_relationships(conn_data, entity_types)
    element_classes = _load_element_classes(entity_data)
    reference_types_raw: dict[Any, Any] = conn_data.get("reference_types") or {}
    reference_types = {str(name): str(description) for name, description in reference_types_raw.items()}

    return _AssuranceModule(
        entity_types=entity_types,
        connection_types=connection_types,
        permitted_relationships=permitted,
        element_classes=element_classes,
        derivation_rules=load_composition_rules(package_dir),
        derivation_restrictions=load_derivation_restrictions(package_dir),
        reference_types=reference_types,
    )
