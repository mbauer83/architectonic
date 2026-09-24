"""Which icons of the library a picker offers: those that apply, carry a tag, or match a name.

`applicable_to` is what the picker is choosing for — an entity, by its id, or a type or
specialization, by name — and an icon is offered only if it may be shown there (D12). A retired icon
is not offered; it still draws where it is already used. The filter is here rather than in each
surface, so REST, MCP and the GUI offer the same icons for the same question.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from src.domain.icons.icon_record import IconRecord
from src.domain.ontology_representation.artifact_types import EntityRecord


def offered_icons(
    library: Sequence[IconRecord],
    *,
    applicable_to: str | None = None,
    tag: str | None = None,
    text: str | None = None,
    include_retired: bool = False,
    entity_of: Callable[[str], EntityRecord | None] = lambda _id: None,
) -> list[IconRecord]:
    names = _names_of(applicable_to, entity_of) if applicable_to else None
    needle = (text or "").strip().casefold()
    return [
        icon
        for icon in library
        if (include_retired or icon.metadata.status == "active")
        and (names is None or icon.metadata.applies_to.admits(names))
        and (tag is None or tag in icon.metadata.tags)
        and (not needle or needle in icon.metadata.name.casefold() or needle in icon.metadata.attribution.casefold())
    ]


def _names_of(target: str, entity_of: Callable[[str], EntityRecord | None]) -> frozenset[str]:
    entity = entity_of(target)
    return entity.type_and_specializations if entity is not None else frozenset({target})
