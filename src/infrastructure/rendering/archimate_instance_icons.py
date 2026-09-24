"""Which embedded icon each ArchiMate instance shows, by the alias it is declared under.

The precedence is generic (`application.icons.effective_icons`); what is ArchiMate's here is how an
instance is addressed — the entity's id for its base drawing, the occurrence id for a further one, as
`archimate_occurrences` defines — and where a specialization keeps its default, `notation.icon`. An
icon is drawn at the height of the type glyph it stands in for, whatever size it is stored at.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.application.artifacts.parsing import normalize_puml_alias
from src.application.icons.effective_icons import (
    effective_icon,
    icon_assignments,
    names_most_specific_first,
)
from src.application.puml_alias_declarations import (
    alias_declared_on,
    declaration_keyword,
    picture_declared_on,
    with_label_picture,
)
from src.application.puml_icon_header import (
    icon_key,
    icon_reference,
    is_icon_reference,
    referenced_icon_keys,
    with_icon_block,
)
from src.domain.diagrams.instance_statements import DiagramInstances
from src.domain.icons.icon_ref import IconRef, IconStyle, library_icon_named
from src.domain.icons.resolved_icon import IconSource
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.infrastructure.rendering.archimate_occurrences import instance_id_of, occurrence_entities

#: The drawn height of a badge: the type glyph is a 16 px sprite at scale 1.2.
BADGE_EDGE_PX = 20
#: The drawn height of a figure: the icon is the element, its name beneath.
FIGURE_EDGE_PX = 64


@dataclass(frozen=True, slots=True)
class DrawnIcon:
    """An icon as one declaration draws it: in its style, with the reference each style would use."""

    style: IconStyle
    badge: str
    figure: str

    def as_badge(self) -> DrawnIcon:
        """The same icon beside the name — what an element that contains others shows, a figure being unable to."""
        return DrawnIcon("badge", self.badge, self.figure)


@dataclass(frozen=True, slots=True)
class InstanceIcons:
    #: alias → how its declaration draws its icon.
    by_alias: Mapping[str, DrawnIcon]
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
    addressed = [(instance_id_of(entity), entity) for entity in [*entities, *occurrences]]
    by_alias: dict[str, DrawnIcon] = {}
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
        key, edge = icon_key(shown.icon.render_digest), max(shown.icon.width, shown.icon.height)
        badge, figure = (icon_reference(key, _scale(drawn, edge)) for drawn in (BADGE_EDGE_PX, FIGURE_EDGE_PX))
        by_alias[alias] = DrawnIcon(shown.style, badge, figure)
        pictures[key] = shown.icon.png
    return InstanceIcons(by_alias, pictures)


def _default_for(entity: EntityRecord, specializations: SpecializationCatalog) -> Callable[[str], IconRef | None]:
    def default(name: str) -> IconRef | None:
        info = specializations.get("entity", entity.artifact_type, name)
        target = library_icon_named(info.notation.icon) if info is not None else None
        return IconRef(target) if target is not None else None

    return default


def _scale(drawn_px: int, stored_px: int) -> str:
    return f"{drawn_px / stored_px:.3g}"


class KeptBodyDeclarations(Protocol):
    """What the renderer states about one element of a kept body: its glyph, and its whole declaration."""

    def glyph(self, entity: EntityRecord) -> str: ...

    def declaration(self, entity: EntityRecord, alias: str, icon: DrawnIcon | None) -> str: ...


def restate_instance_icons(
    body: str,
    instances: DiagramInstances,
    declarations: KeptBodyDeclarations,
    specializations: SpecializationCatalog,
) -> str:
    """*body* showing each instance's icon as the diagram now states it, for a body kept as written.

    A declaration whose instance has an icon shows it; one that shows an icon the diagram no longer
    assigns gets its type glyph back. Only the picture changes — unless the element changes kind,
    becoming a figure or ceasing to be one, when its declaration is stated afresh (keeping its
    indentation). An instance the body does not declare is left alone: there is nothing to change and
    nothing is invented.
    """
    entities = [entity for entity in map(instances.entity_of, instances.entity_ids) if entity is not None]
    occurrences = occurrence_entities(instances.diagram_entities, {e.artifact_id: e for e in entities})
    icons = instance_icons(instances.diagram_entities, entities, occurrences, instances.icon_source, specializations)
    if not icons.by_alias and not referenced_icon_keys(body):
        return body
    by_alias = {normalize_puml_alias(e.display_alias): e for e in [*entities, *occurrences]}
    repictured = "\n".join(_repictured(line, icons, by_alias, declarations) for line in body.split("\n"))
    return with_icon_block(repictured, icons.pictures)


def _repictured(
    line: str, icons: InstanceIcons, by_alias: Mapping[str, EntityRecord], declarations: KeptBodyDeclarations
) -> str:
    declaration = alias_declared_on(line)
    entity = by_alias.get(declaration.alias) if declaration is not None else None
    if declaration is None or entity is None:
        return line
    icon = icons.by_alias.get(declaration.alias)
    opens_block = line.rstrip().endswith("{")
    wants_figure = icon is not None and icon.style == "figure" and not opens_block
    if wants_figure != (declaration_keyword(line) == "label"):
        indent = line[: len(line) - len(line.lstrip())]
        return indent + declarations.declaration(entity, declaration.alias, icon)
    if icon is not None:
        return with_label_picture(line, icon.badge)
    if is_icon_reference(picture_declared_on(line)):
        return with_label_picture(line, declarations.glyph(entity))
    return line
