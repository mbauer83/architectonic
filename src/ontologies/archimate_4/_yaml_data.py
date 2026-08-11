"""YAML data-file loaders for the archimate-4 module: entity and connection types, the permitted
relationships they may form, element classes, the specialization catalog and the named-profile
registry.

Kept out of ``_loader.py`` so the module loader stays within the source-length policy and the
file-reading is one small, testable place. ``_loader.py`` is then only the module class and the
assembly step — what the module *is*, rather than how each of its declarations is parsed.

``META_ONTOLOGY_ALIAS`` lives here because the guidance overlay is keyed by it and the parsing
functions below need it. ``_loader`` re-exports it, so the alias is still reached where callers
already look for it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast

from src.domain.assurance.aibom_roles import DerivationRoleBindings, role_bindings_from_mapping
from src.domain.guidance.guidance import ConceptKind, GuidanceOverlay, resolved_type_guidance
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_types import (
    ConnectionTypeInfo,
    ElementClassInfo,
    EntityTypeInfo,
)
from src.domain.ontology_representation.profile_registry import ProfileRegistry, profile_registry_from_mapping
from src.domain.ontology_representation.relation_notation import parse_relation_notation
from src.domain.ontology_representation.specializations import (
    SpecializationCatalog,
    specialization_catalog_from_mapping,
)
from src.domain.relationships.permitted_relationships import (
    PermittedRelationship,
    PermittedRelationshipSet,
)
from src.domain.yaml_documents import parse_yaml

META_ONTOLOGY_ALIAS = "archimate-4"

DerivationRole = Literal["structural", "dependency", "dynamic", "specialization"]


def load_module_specializations(package_dir: Path, module_alias: str) -> SpecializationCatalog:
    path = package_dir / "specializations.yaml"
    if not path.exists():
        return SpecializationCatalog.empty()
    loaded: Any = parse_yaml(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid specialization declarations in {path}: top-level YAML value must be a mapping")
    return specialization_catalog_from_mapping(loaded, module_alias=module_alias)


def load_module_profiles(package_dir: Path) -> ProfileRegistry:
    path = package_dir / "profiles.yaml"
    if not path.exists():
        return ProfileRegistry.empty()
    return profile_registry_from_mapping(parse_yaml(path.read_text(encoding="utf-8")), label=str(path))


def load_module_aibom_roles(package_dir: Path) -> DerivationRoleBindings:
    path = package_dir / "aibom_roles.yaml"
    if not path.exists():
        return DerivationRoleBindings.empty()
    return role_bindings_from_mapping(parse_yaml(path.read_text(encoding="utf-8")), label=str(path))


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


def load_entity_types(
    data: dict[str, Any], guidance: GuidanceOverlay | None = None
) -> dict[EntityTypeName, EntityTypeInfo]:
    overlay = guidance if guidance is not None else GuidanceOverlay()
    out: dict[EntityTypeName, EntityTypeInfo] = {}
    for artifact_type, info in data["entity_types"].items():
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


def load_connection_types(
    data: dict[str, Any], guidance: GuidanceOverlay | None = None
) -> dict[ConnectionTypeName, ConnectionTypeInfo]:
    overlay = guidance if guidance is not None else GuidanceOverlay()
    out: dict[ConnectionTypeName, ConnectionTypeInfo] = {}
    derivation_strengths: dict[str, set[int]] = {}
    for lang, types in data["connection_types"].items():
        for name, info in cast(dict[str, Any | None], types or {}).items():
            raw: dict[str, Any] = info or {}
            create_when, never_create_when = _type_guidance(overlay, "connection", name, raw)
            hp_raw = raw.get("hierarchy_priority")
            derivation_role, derivation_strength = _parse_derivation(raw.get("derivation"), name)
            if derivation_strength is not None and derivation_role is not None:
                strengths = derivation_strengths.setdefault(derivation_role, set())
                if derivation_strength in strengths:
                    raise ValueError(f"connection type {name!r}: duplicate derivation strength {derivation_strength}")
                strengths.add(derivation_strength)
            out[ConnectionTypeName(name)] = ConnectionTypeInfo(
                artifact_type=name,
                conn_lang=lang,
                create_when=create_when,
                never_create_when=never_create_when,
                archimate_relationship_type=raw.get("archimate_relationship_type"),
                symmetric=bool(raw.get("symmetric", False)),
                puml_arrow=raw.get("puml_arrow", "-->"), notation=parse_relation_notation(raw.get("notation")),
                show_stereotype=bool(raw.get("show_stereotype", "puml_arrow" not in raw)),
                classes=tuple(raw.get("classes", ())),
                hierarchy_priority=int(hp_raw) if hp_raw is not None else None,
                hierarchy_label=str(raw["hierarchy_label"]) if raw.get("hierarchy_label") else None,
                bidirectional_sync=bool(raw.get("bidirectional_sync", False)),
                relationship_kind=str(raw["relationship_kind"]) if raw.get("relationship_kind") else None,
                derivation_role=derivation_role,
                derivation_strength=derivation_strength,
            )
    return out


def _parse_derivation(raw: object, name: str) -> tuple[DerivationRole | None, int | None]:
    if raw is None:
        return None, None
    if not isinstance(raw, Mapping):
        raise ValueError(f"connection type {name!r}: derivation must be a mapping")
    role = raw.get("role")
    valid_roles = {"structural", "dependency", "dynamic", "specialization"}
    if role not in valid_roles:
        raise ValueError(f"connection type {name!r}: unknown derivation role {role!r}")
    has_strength = "strength" in raw
    strength = raw.get("strength")
    if role in {"structural", "dependency"}:
        if not isinstance(strength, int) or isinstance(strength, bool):
            raise ValueError(f"connection type {name!r}: derivation role {role!r} requires an integer strength")
        return cast(DerivationRole, role), strength
    if has_strength:
        raise ValueError(f"connection type {name!r}: derivation role {role!r} forbids strength")
    return cast(DerivationRole, role), None


def _expand_ref(
    ref: str | list[Any],
    all_types: list[str],
    class_members: dict[str, list[str]],
) -> list[str]:
    if isinstance(ref, list):
        out: list[str] = []
        for item in ref:
            out.extend(_expand_ref(item, all_types, class_members))
        return out
    if ref == "@all":
        return list(all_types)
    if ref.startswith("@"):
        return list(class_members.get(ref[1:], []))
    return [ref]


def build_permitted_relationships(
    data: dict[str, Any],
    entity_types: dict[EntityTypeName, EntityTypeInfo],
) -> PermittedRelationshipSet:
    all_types: list[str] = [str(k) for k in entity_types.keys()]

    class_members: dict[str, list[str]] = {}
    for ename, info in entity_types.items():
        for cls in info.classes:
            class_members.setdefault(cls, []).append(str(ename))

    rules: set[PermittedRelationship] = set()

    for rule in data.get("permitted_relationships", []):
        raw_src, raw_tgt, raw_conn_shorts = rule
        conn_types = [ConnectionTypeName(f"archimate-{t}") for t in raw_conn_shorts]
        sources = _expand_ref(raw_src, all_types, class_members)

        for src in sources:
            targets = [src] if raw_tgt == "@same" else _expand_ref(raw_tgt, all_types, class_members)
            for tgt in targets:
                for ct in conn_types:
                    rules.add(
                        PermittedRelationship(
                            source_type=EntityTypeName(src),
                            target_type=EntityTypeName(tgt),
                            connection_type=ct,
                        )
                    )

    return PermittedRelationshipSet(frozenset(rules))


def load_element_classes(data: dict[str, Any]) -> dict[str, ElementClassInfo]:
    raw_classes: dict[str, Any] = data.get("element_classes") or {}
    out: dict[str, ElementClassInfo] = {}
    for ec_name, ec_info in raw_classes.items():
        raw: dict[str, Any] = ec_info or {}
        out[str(ec_name)] = ElementClassInfo(
            name=str(ec_name),
            description=str(raw.get("description") or ""),
        )
    return out
