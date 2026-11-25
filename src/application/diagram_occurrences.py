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
from src.domain.artifact_id import canonical_entity_key
from src.domain.ontology_representation.artifact_types import EntityRecord


def occurrence_statements(diagram_entities: Mapping[str, object] | None) -> list[tuple[str, str]]:
    """Every occurrence statement as ``(occurrence id, backing entity id)``, in the order stated.

    The one reading of what makes an item an occurrence: it names both an ``id`` and a
    ``backing_entity_id``. The backing entity is answered by its stable id, whichever spelling the
    statement used, so a short id draws the element as the slugged one does. Whoever needs the further
    drawings of a diagram — to render them, to resolve their aliases, to know which instance ids a
    layout may name — starts here.
    """
    return [
        (occurrence_id, canonical_entity_key(backing_id))
        for items in (diagram_entities or {}).values() if isinstance(items, list)
        for item in items if isinstance(item, dict)
        if (backing_id := str(item.get("backing_entity_id") or "").strip())
        and (occurrence_id := str(item.get("id") or "").strip())
    ]


def occurrence_entities(
    diagram_entities: Mapping[str, object] | None,
    entity_by_id: Mapping[str, EntityRecord],
) -> list[EntityRecord]:
    """Return additional rendered occurrences declared in diagram-entities."""
    counts: dict[str, int] = {}
    result: list[EntityRecord] = []
    by_stable_id = {canonical_entity_key(entity_id): entity for entity_id, entity in entity_by_id.items()}
    for occurrence_id, backing_id in occurrence_statements(diagram_entities):
        backing = by_stable_id.get(backing_id)
        if backing is None or not backing.display_alias:
            continue
        base_alias = normalize_puml_alias(backing.display_alias)
        if not base_alias:
            continue
        counts[backing_id] = counts.get(backing_id, 1) + 1
        result.append(
            replace(
                backing,
                display_alias=occurrence_alias(base_alias, counts[backing_id]),
                host_diagram_id=occurrence_id,
            )
        )
    return result


def occurrence_alias(base_alias: str, drawing: int) -> str:
    """The alias of the *drawing*-th drawing of an element whose first is *base_alias*; counted from 2."""
    return f"{base_alias}__{drawing}"


def backing_entity_ids(diagram_entities: Mapping[str, object] | None) -> list[str]:
    """The model elements this diagram's occurrence statements draw again, read as `occurrence_entities` reads them."""
    return [backing_id for _occurrence, backing_id in occurrence_statements(diagram_entities)]
