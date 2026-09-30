"""Which embedded icon each drawn element shows, for any notation: the one join from statements to pictures.

A notation says how it addresses and names what it draws — an ArchiMate instance by its entity or
occurrence id and its type and specializations, a C4 node by its local id and its type — and how
large it draws an icon, in which form. This module answers the rest once: the precedence
(`application.icons.effective_icons`), the content-addressed key, and the pictures the body's icon
block embeds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.application.icons.effective_icons import effective_icon, icon_assignments
from src.application.puml_icon_header import icon_key, icon_reference, sprite_reference, with_icon_block
from src.domain.icons.icon_ref import IconRef, IconStyle
from src.domain.icons.render_form import IconBox
from src.domain.icons.resolved_icon import IconSource


@dataclass(frozen=True, slots=True)
class DrawnElement:
    """One element as its renderer declares it: the id statements name it by, its names, its alias."""

    instance_id: str
    #: Its applied specializations in order, then its type.
    names: tuple[str, ...]
    alias: str
    specialization_default: Callable[[str], IconRef | None] | None = None


@dataclass(frozen=True, slots=True)
class ShownIcon:
    key: str
    width_px: int
    height_px: int
    style: IconStyle

    def reference(self, box: IconBox) -> str:
        """The icon inside a label, `<img:$ARCH_ICON_…{scale=…}>`, fitted into *box*."""
        return icon_reference(self.key, self._scale(box))

    def sprite(self, box: IconBox) -> str:
        """The icon as a macro's image parameter, `img:$ARCH_ICON_…{scale=…}`, fitted into *box*."""
        return sprite_reference(self.key, self._scale(box))

    def _scale(self, box: IconBox) -> str:
        return f"{box.scale_for(self.width_px, self.height_px):.3g}"


@dataclass(frozen=True, slots=True)
class ElementIcons:
    by_alias: Mapping[str, ShownIcon]
    #: icon key → the picture the body's icon block embeds under it.
    pictures: Mapping[str, bytes]

    def embedded_in(self, body: str) -> str:
        """*body* with the icon block its references need."""
        return with_icon_block(body, self.pictures)


NO_ELEMENT_ICONS = ElementIcons({}, {})


def element_icons(
    diagram_entities: Mapping[str, object] | None,
    elements: Sequence[DrawnElement],
    source: IconSource | None,
) -> ElementIcons:
    if source is None:
        return NO_ELEMENT_ICONS
    assignments = icon_assignments(diagram_entities)
    by_alias: dict[str, ShownIcon] = {}
    pictures: dict[str, bytes] = {}
    for element in elements:
        default = element.specialization_default or (lambda _name: None)
        shown = effective_icon(element.instance_id, element.names, assignments, source, default)
        if shown is None:
            continue
        key = icon_key(shown.icon.render_digest)
        by_alias[element.alias] = ShownIcon(key, shown.icon.width, shown.icon.height, shown.style)
        pictures[key] = shown.icon.png
    return ElementIcons(by_alias, pictures)
