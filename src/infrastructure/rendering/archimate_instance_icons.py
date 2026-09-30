"""Which embedded icon each ArchiMate instance shows, by the alias it is declared under.

The join from statements to pictures is generic (`drawn_element_icons`); what is ArchiMate's here is
how an instance is addressed — the entity's id for its base drawing, the occurrence id for a further one, as
`archimate_occurrences` defines — and where a specialization keeps its default, `notation.icon`. An
icon is drawn at the height of the type glyph it stands in for, whatever size it is stored at.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.application.artifacts.parsing import normalize_puml_alias
from src.application.icons.effective_icons import names_most_specific_first, specialization_defaults
from src.application.puml_alias_declarations import (
    alias_declared_on,
    declares_an_icon_figure,
    picture_declared_on,
    with_label_picture,
)
from src.application.puml_icon_header import is_icon_reference, referenced_icon_keys, with_icon_block
from src.domain.diagrams.instance_statements import DiagramInstances
from src.domain.icons.icon_ref import IconStyle
from src.domain.icons.render_form import IconBox
from src.domain.icons.resolved_icon import IconSource
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.infrastructure.rendering.archimate_occurrences import instance_id_of, occurrence_entities
from src.infrastructure.rendering.drawn_element_icons import DrawnElement, element_icons

#: A badge stands where the type glyph stands, a 16 px sprite at scale 1.2, so it takes the glyph's
#: height; a wordmark may run to three times that beside the name.
BADGE_BOX = IconBox(height_px=20, max_width_px=60)
#: A figure is the element, its name beneath: the height of a small element, and room for a wordmark.
FIGURE_BOX = IconBox(height_px=64, max_width_px=160)


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



def instance_icons(
    diagram_entities: Mapping[str, object] | None,
    entities: Sequence[EntityRecord],
    occurrences: Sequence[EntityRecord],
    source: IconSource | None,
    specializations: SpecializationCatalog,
) -> InstanceIcons:
    elements = [
        DrawnElement(
            instance_id_of(entity),
            names_most_specific_first(entity.artifact_type, entity.specializations),
            alias,
            specialization_defaults(entity.artifact_type, specializations),
        )
        for entity in [*entities, *occurrences]
        if (alias := normalize_puml_alias(entity.display_alias))
    ]
    shown = element_icons(diagram_entities, elements, source)
    return InstanceIcons(
        {
            alias: DrawnIcon(icon.style, icon.reference(BADGE_BOX), icon.reference(FIGURE_BOX))
            for alias, icon in shown.by_alias.items()
        },
        shown.pictures,
    )


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
    wants_figure = icon is not None and icon.style == "figure" and not line.rstrip().endswith("{")
    if wants_figure or declares_an_icon_figure(line):
        # A figure's line is wholly the renderer's statement — picture, line break, name — so it is
        # stated afresh whenever it is, or was, a figure, rather than re-pictured in place.
        indent = line[: len(line) - len(line.lstrip())]
        return indent + declarations.declaration(entity, declaration.alias, icon)
    if icon is not None:
        return with_label_picture(line, icon.badge)
    if is_icon_reference(picture_declared_on(line)):
        return with_label_picture(line, declarations.glyph(entity))
    return line
