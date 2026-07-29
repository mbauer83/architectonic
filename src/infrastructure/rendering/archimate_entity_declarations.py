"""Entity declaration helpers for generic ArchiMate-style PlantUML rendering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.domain.modules.module_types import EntityTypeName
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.ontology_representation.specializations import SpecializationCatalog, SpecializationInfo
from src.domain.viewpoints.viewpoint_condition_evaluation import read_attribute_value
from src.infrastructure.rendering._archimate_includes import parse_archimate_display_block
from src.infrastructure.rendering._diagram_text import pluralize_label
from src.infrastructure.rendering.archimate_relation_rendering import format_specializations_guillemet
from src.infrastructure.rendering.generic_puml_layout import ordered_type_groups

#: Sprite scale applied to every entity icon, so the glyph sits proportionately beside the label.
#: Named once because it appears in more than one declaration form, and two copies of a rendering
#: constant drift the moment one is tuned.
ICON_SCALE = "1.2"


def stereotype_key(artifact_type: str) -> str:
    return artifact_type.replace("-", "_")


def grouping_key(entity: EntityRecord, registry: Any) -> str:
    info = registry.find_entity_type(EntityTypeName(entity.artifact_type))
    if info is not None and info.hierarchy:
        return info.hierarchy[0]
    return (entity.domain or "common").lower()


def ordered_domains(domain_entities: Mapping[str, list[EntityRecord]], registry: Any) -> list[str]:
    ordered: list[str] = []
    for domain in registry.domain_order():
        if domain in domain_entities:
            ordered.append(domain)
    for domain in sorted(domain_entities):
        if domain not in ordered:
            ordered.append(domain)
    return ordered


def grouping_stereotype(config: Mapping[str, Any], grouping_key_value: str) -> str:
    grouping = config.get("grouping", {})
    if not isinstance(grouping, dict):
        return grouping_key_value.capitalize() + "Grouping"
    pattern = str(grouping.get("stereotype_pattern", "{hierarchy_0|capitalize}Grouping"))
    return (
        pattern.replace("{hierarchy_0|capitalize}", grouping_key_value.capitalize())
        .replace("{hierarchy_0}", grouping_key_value)
        .replace("{domain_dir|capitalize}", grouping_key_value.capitalize())
        .replace("{domain_dir}", grouping_key_value)
    )


def entity_declaration(
    entity: EntityRecord,
    alias: str,
    registry: Any,
    junction_types: frozenset[str],
    specialization_catalog: SpecializationCatalog = SpecializationCatalog.empty(),
    *,
    label_attribute: str | None = None,
) -> str:
    if entity.artifact_type in junction_types:
        return f'circle " " as {alias}'
    label, stereotype, spec = entity_label_and_stereotype(
        entity, registry, specialization_catalog, label_attribute=label_attribute
    )
    icon_key, color_suffix, show_icon = _specialization_notation(stereotype, spec, entity_has_sprite(entity, registry))
    if show_icon and icon_key:
        return (
            f'rectangle "<$archimate_{icon_key}{{scale={ICON_SCALE}}}> {label}" '
            f'<<{stereotype}>> as {alias}{color_suffix}'
        )
    if stereotype:
        return f'rectangle "{label}" <<{stereotype}>> as {alias}{color_suffix}'
    return f'rectangle "{label}" as {alias}{color_suffix}'


def entity_nest_declaration(
    entity: EntityRecord,
    alias: str,
    registry: Any,
    junction_types: frozenset[str],
    specialization_catalog: SpecializationCatalog = SpecializationCatalog.empty(),
    *,
    label_attribute: str | None = None,
) -> str:
    if entity.artifact_type in junction_types:
        return f'circle " " as {alias}'
    label, stereotype, spec = entity_label_and_stereotype(
        entity, registry, specialization_catalog, label_attribute=label_attribute
    )
    icon_key, color_suffix, show_icon = _specialization_notation(stereotype, spec, entity_has_sprite(entity, registry))
    if show_icon and icon_key:
        return (
            f'rectangle "<$archimate_{icon_key}{{scale={ICON_SCALE}}}> {label}" '
            f'<<{stereotype}>> as {alias}{color_suffix} {{'
        )
    if stereotype:
        return f'rectangle "{label}" <<{stereotype}>> as {alias}{color_suffix} {{'
    return f'rectangle "{label}" as {alias}{color_suffix} {{'


def _specialization_notation(
    stereotype: str | None, spec: SpecializationInfo | None, parent_has_sprite: bool
) -> tuple[str | None, str, bool]:
    """Return (sprite_icon_key, color_suffix, show_icon) — the specialization's own notation
    when declared, falling back to the parent type's stereotype key/sprite availability
    otherwise. A specialization's own icon is always shown even when the parent type has no
    sprite of its own; without one, showing the icon syntax at all depends on the parent."""
    has_own_icon = spec is not None and bool(spec.notation.icon)
    icon_key = spec.notation.icon if has_own_icon and spec is not None else stereotype
    color_suffix = f" #{spec.notation.color}" if spec is not None and spec.notation.color else ""
    return icon_key, color_suffix, has_own_icon or parent_has_sprite


def ordered_entity_type_groups(entities: list[EntityRecord], registry: Any) -> list[tuple[str, list[EntityRecord]]]:
    return ordered_type_groups(
        entities,
        type_order=[str(k) for k in registry.all_entity_types()],
        label_by_type={
            entity.artifact_type: pluralize_label(
                (registry.find_entity_type(EntityTypeName(entity.artifact_type)) or entity)
                .artifact_type.replace("-", " ")
                .title()
            )
            for entity in entities
        },
    )


def entity_label_and_stereotype(
    entity: EntityRecord,
    registry: Any,
    specialization_catalog: SpecializationCatalog = SpecializationCatalog.empty(),
    *,
    label_attribute: str | None = None,
) -> tuple[str, str | None, SpecializationInfo | None]:
    section_id = display_section_id(entity, registry)
    raw_block = entity.display_blocks.get(section_id, "")
    archimate_block = parse_archimate_display_block(raw_block)
    label = str(archimate_block.get("label") or entity.display_label or entity.name).replace('"', "'")
    info = registry.find_entity_type(EntityTypeName(entity.artifact_type))
    stereotype = stereotype_key(info.artifact_type) if isinstance(info, EntityTypeInfo) else None
    # All applied specializations show in the label (§15.2 comma-separated list); the PRIMARY
    # one drives notation (icon/color) below, since a single glyph cannot honour several.
    resolved = [
        specialization_catalog.get("entity", entity.artifact_type, slug) for slug in entity.specializations
    ]
    spec: SpecializationInfo | None = next((info for info in resolved if info is not None), None)
    guillemet = format_specializations_guillemet([info.name for info in resolved if info is not None])
    if guillemet:
        # Its own line, not trailing the name. On one line the guillemets read as part of the
        # element's name and stretch the node to the width of both, which is what pushed the
        # generated ArchiMate figures wide enough to lose their flow.
        label = f"{label}\\n{guillemet}"
    if label_attribute:
        value, present = read_attribute_value(entity, label_attribute, context="entity")
        if present and value is not None:
            value_text = str(value).replace('"', "'")
            label = f"{label}\\n{value_text}"
    return label, stereotype, spec


def display_section_id(entity: EntityRecord, registry: Any) -> str:
    ontology = registry.ontology_for_entity_type(EntityTypeName(entity.artifact_type))
    if ontology is not None:
        return ontology.display_section_id
    return "archimate"


def entity_has_sprite(entity: EntityRecord, registry: Any) -> bool:
    ontology = registry.ontology_for_entity_type(EntityTypeName(entity.artifact_type))
    return ontology is not None and ontology.sprite_for(entity.artifact_type) is not None
