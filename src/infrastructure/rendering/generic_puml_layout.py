"""Layout helper functions for generic PUML rendering."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from src.application.artifact_parsing import normalize_puml_alias
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.infrastructure.rendering._diagram_layout import build_visual_nesting
from src.infrastructure.rendering._diagram_text import pluralize_label


def ordered_type_groups(
    entities: Sequence[EntityRecord],
    *,
    type_order: Sequence[str],
    label_by_type: Mapping[str, str],
) -> list[tuple[str, list[EntityRecord]]]:
    grouped: dict[str, list[EntityRecord]] = defaultdict(list)
    for entity in entities:
        grouped[entity.artifact_type].append(entity)

    ordered_types = [artifact_type for artifact_type in type_order if artifact_type in grouped]
    for artifact_type in grouped:
        if artifact_type not in ordered_types:
            ordered_types.append(artifact_type)

    return [
        (
            label_by_type.get(artifact_type) or pluralize_label(artifact_type.replace("-", " ").title()),
            grouped[artifact_type],
        )
        for artifact_type in ordered_types
    ]


def build_generic_visual_nesting(
    *,
    entities: Sequence[EntityRecord],
    connections: Sequence[ConnectionRecord],
    alias_by_id: Mapping[str, str],
    entity_by_alias: Mapping[str, EntityRecord],
    nesting_connection_types: frozenset[str],
    junction_entity_types: frozenset[str],
    flow_through_entity_types: frozenset[str] = frozenset(),
) -> tuple[dict[str, list[EntityRecord]], set[str]]:
    entity_order = {
        normalize_puml_alias(entity.display_alias): index
        for index, entity in enumerate(entities)
        if entity.display_alias
    }
    structural_edges: list[tuple[str, str]] = []
    neighbor_edges: list[tuple[str, str]] = []
    for conn in connections:
        src_alias = alias_by_id.get(conn.source)
        tgt_alias = alias_by_id.get(conn.target)
        if not src_alias or not tgt_alias:
            continue
        if conn.conn_type in nesting_connection_types and tgt_alias in entity_by_alias:
            structural_edges.append((src_alias, tgt_alias))
            continue
        neighbor_edges.append((src_alias, tgt_alias))

    children_map, nested_aliases = build_visual_nesting(
        item_by_alias=dict(entity_by_alias),
        structural_edges=structural_edges,
        neighbor_edges=neighbor_edges,
        junction_aliases={
            alias for alias, entity in entity_by_alias.items() if entity.artifact_type in junction_entity_types
        },
        flow_through_aliases={
            alias
            for alias, entity in entity_by_alias.items()
            if entity.artifact_type in flow_through_entity_types
        },
    )
    for children in children_map.values():
        children.sort(
            key=lambda entity: entity_order.get(
                normalize_puml_alias(entity.display_alias),
                len(entity_order),
            )
        )
    return children_map, nested_aliases
