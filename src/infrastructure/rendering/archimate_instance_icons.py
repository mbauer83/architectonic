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
    effective_icon,
    icon_assignments,
    names_most_specific_first,
)
from src.application.puml_alias_declarations import alias_declared_on, picture_declared_on, with_label_picture
from src.application.puml_icon_header import (
    icon_key,
    icon_reference,
    is_icon_reference,
    referenced_icon_keys,
    with_icon_block,
)
from src.domain.diagrams.instance_statements import DiagramInstances
from src.domain.icons.icon_ref import IconRef, library_icon_named
from src.domain.icons.resolved_icon import IconSource
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.infrastructure.rendering.archimate_occurrences import occurrence_entities

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


def restate_instance_icons(
    body: str,
    instances: DiagramInstances,
    glyph_of: Callable[[EntityRecord], str],
    specializations: SpecializationCatalog,
) -> str:
    """*body* showing each instance's icon as the diagram now states it, for a body kept as written.

    A declaration whose instance has an icon shows it; one that shows an icon the diagram no longer
    assigns gets its type glyph back. Nothing else on any line changes, and an instance the body does
    not declare is left alone — there is no line to change and nothing is invented.
    """
    entities = [entity for entity in map(instances.entity_of, instances.entity_ids) if entity is not None]
    occurrences = occurrence_entities(instances.diagram_entities, {e.artifact_id: e for e in entities})
    icons = instance_icons(instances.diagram_entities, entities, occurrences, instances.icon_source, specializations)
    if not icons.by_alias and not referenced_icon_keys(body):
        return body
    glyph_by_alias = {normalize_puml_alias(e.display_alias): glyph_of(e) for e in [*entities, *occurrences]}
    repictured = "\n".join(_repictured(line, icons, glyph_by_alias) for line in body.split("\n"))
    return with_icon_block(repictured, icons.pictures)


def _repictured(line: str, icons: InstanceIcons, glyph_by_alias: Mapping[str, str]) -> str:
    declaration = alias_declared_on(line)
    if declaration is None:
        return line
    if (icon := icons.by_alias.get(declaration.alias)) is not None:
        return with_label_picture(line, icon)
    if is_icon_reference(picture_declared_on(line)):
        return with_label_picture(line, glyph_by_alias.get(declaration.alias, ""))
    return line
