"""Which further drawings an ArchiMate diagram's occurrence statements add, and the alias each is drawn under.

The one reading of an ``occurrence`` statement (``{id, backing_entity_id}``): the renderer draws what it
returns, and the verifier resolves the aliases it assigns — a second drawing of a model element is
``{base alias}__{n}``. It sat in the rendering layer, where the verifier could not reach it, so the
completeness rules did not know an occurrence alias and reported it as resolving to nothing (B112).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from src.application.artifacts.parsing import normalize_puml_alias
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


def backing_entity_ids(diagram_entities: Mapping[str, object] | None) -> list[str]:
    """The model elements this diagram's occurrence statements draw again, read as `occurrence_entities` reads them."""
    return [
        backing_id
        for items in (diagram_entities or {}).values() if isinstance(items, list)
        for item in items if isinstance(item, dict)
        if (backing_id := str(item.get("backing_entity_id") or "").strip())
    ]
