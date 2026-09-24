"""Which embedded icon each ArchiMate instance shows, by the alias it is declared under.

The precedence is generic (`application.icons.effective_icons`); what is ArchiMate's here is how an
instance is addressed — the entity's id for its base drawing, the occurrence id for a further one, as
`archimate_occurrences` defines — and where a specialization keeps its default, `notation.icon`. An
icon is drawn at the height of the type glyph it stands in for, whatever size it is stored at.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.application.artifacts.parsing import normalize_puml_alias
from src.application.icons.effective_icons import (
    IconSource,
    effective_icon,
    icon_assignments,
    names_most_specific_first,
)
from src.application.puml_icon_header import icon_key, icon_reference
from src.domain.icons.icon_ref import IconRef, library_icon_named
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.specializations import SpecializationCatalog

#: The drawn height of a badge: the type glyph is a 16 px sprite at scale 1.2.
BADGE_EDGE_PX = 20


@dataclass(frozen=True, slots=True)
class InstanceIcons:
    #: alias → the `<img:$ARCH_ICON_…{scale=…}>` its declaration shows.
    by_alias: Mapping[str, str]
    #: icon key → the picture the body's icon block embeds under it.
    pictures: Mapping[str, bytes]


NO_ICONS = InstanceIcons({}, {})


def instance_icons(
    diagram_entities: Mapping[str, object] | None,
    entities: Sequence[EntityRecord],
    occurrences: Sequence[EntityRecord],
    source: IconSource | None,
    specializations: SpecializationCatalog,
) -> InstanceIcons:
    if source is None:
        return NO_ICONS
    assignments = icon_assignments(diagram_entities)
    addressed = [(entity.artifact_id, entity) for entity in entities] + [
        (occurrence.host_diagram_id or "", occurrence) for occurrence in occurrences
    ]
    by_alias: dict[str, str] = {}
    pictures: dict[str, bytes] = {}
    for instance_id, entity in addressed:
        alias = normalize_puml_alias(entity.display_alias)
        if not alias:
            continue
        shown = effective_icon(
            instance_id,
            names_most_specific_first(entity.artifact_type, entity.specializations),
            assignments,
            source,
            _default_for(entity, specializations),
        )
        if shown is None:
            continue
        key = icon_key(shown.icon.render_digest)
        by_alias[alias] = icon_reference(key, _scale(max(shown.icon.width, shown.icon.height)))
        pictures[key] = shown.icon.png
    return InstanceIcons(by_alias, pictures)


def _default_for(entity: EntityRecord, specializations: SpecializationCatalog) -> Callable[[str], IconRef | None]:
    def default(name: str) -> IconRef | None:
        info = specializations.get("entity", entity.artifact_type, name)
        target = library_icon_named(info.notation.icon) if info is not None else None
        return IconRef(target) if target is not None else None

    return default


def _scale(edge_px: int) -> str:
    return f"{BADGE_EDGE_PX / edge_px:.3g}"
