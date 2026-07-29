"""Occurrence helpers for ArchiMate-style renderers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from src.application.artifact_parsing import normalize_puml_alias
from src.domain.ontology_representation.artifact_types import EntityRecord


def occurrence_entities(
    diagram_entities: Mapping[str, object] | None,
    entity_by_id: Mapping[str, EntityRecord],
) -> list[EntityRecord]:
    """Return additional rendered occurrences declared in diagram-entities."""
    if not diagram_entities:
        return []

    counts: dict[str, int] = {}
    result: list[EntityRecord] = []
    for items in diagram_entities.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            backing_id = str(item.get("backing_entity_id") or "").strip()
            occurrence_id = str(item.get("id") or "").strip()
            if not backing_id or not occurrence_id:
                continue
            backing = entity_by_id.get(backing_id)
            if backing is None or not backing.display_alias:
                continue
            base_alias = normalize_puml_alias(backing.display_alias)
            if not base_alias:
                continue
            counts[backing_id] = counts.get(backing_id, 1) + 1
            result.append(
                replace(
                    backing,
                    display_alias=f"{base_alias}__{counts[backing_id]}",
                    host_diagram_id=occurrence_id,
                )
            )
    return result
