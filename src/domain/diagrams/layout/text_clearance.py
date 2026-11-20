"""A line never passes through text: where a picture's text lies, and whether a course passes through it.

Text is everything a reader reads on a picture: an element's label, a box's title together with the
band across the box it sits in, a relation's label, and what is drawn around the diagram — its title
and legend. Each occupies a **text region**: the rectangle its words are set in, padded, and for a
box the band from its top edge to below its title, a margin wider than the title on each side. A line may end at an
element's border; it never enters a text region. The router keeps routes out of them, the label
placer keeps labels off routes, and the rendered-picture check reports a picture where a line does
enter one (W380).

A word is known by its baseline and the width the renderer measured; its height is the renderer's
label font's, stated here once. Mirrored in `tools/gui/src/domain/layout/textClearance.ts` from the
shared fixtures, which hold the predicate both languages apply.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import DrawnBox, MeasuredWord, RenderedPicture

#: How far a line of text reaches above its baseline, and below it, in the renderer's label font.
ABOVE_BASELINE, BELOW_BASELINE = 11.0, 3.0

#: The room kept round text, which a line keeps out of too.
TEXT_PADDING = 3.0

#: How far a title band reaches beyond its title on either side.
BAND_MARGIN = 24.0

#: How far into a text region a line must run before it counts as through it: a line ending on a
#: region's edge, or grazing it, has not.
_THROUGH_MARGIN = 1.0


def text_extent(words: Sequence[MeasuredWord]) -> Extent | None:
    """The rectangle a run of words is set in, or None for no words."""
    if not words:
        return None
    return Extent(
        min(word.start.x for word in words), min(word.start.y for word in words) - ABOVE_BASELINE,
        max(word.end_x for word in words), max(word.start.y for word in words) + BELOW_BASELINE,
    )


def padded(extent: Extent, by: float = TEXT_PADDING) -> Extent:
    return Extent(extent.left - by, extent.top - by, extent.right + by, extent.bottom + by)


def title_band(box: Extent, title: Extent) -> Extent:
    """The band a box's title sits in: from the box's top edge to below the title, and as wide as the
    title with `BAND_MARGIN` either side, within the box.

    Not the box's whole width: a domain box's title band across the whole diagram would leave a
    relation from outside no way in but round the side, and the pictures that tried it were drawn
    with every such line detouring round the whole diagram.
    """
    return Extent(
        max(box.left, title.left - BAND_MARGIN), box.top,
        min(box.right, title.right + BAND_MARGIN), min(box.bottom, title.bottom + TEXT_PADDING),
    )


@dataclass(frozen=True)
class TextRegion:
    """One place text is set, and what it is the text of.

    *of* names it by the aliases of the picture: a box or an element by its own, a relation's label
    by the relation's two ends, and the diagram's own title or legend by nothing.
    """

    extent: Extent
    of: tuple[str, ...]


def _box_band(box: DrawnBox) -> TextRegion | None:
    title = text_extent(box.words)
    return TextRegion(title_band(box.extent, title), (box.alias,)) if title is not None else None


def text_regions(picture: RenderedPicture, around: Sequence[Sequence[MeasuredWord]] = ()) -> tuple[TextRegion, ...]:
    """Every text region of *picture*; *around* is the text drawn round the diagram, such as its legend.

    An element's label set inside the element is its outline's business, not a region of its own: a
    line through it is already a line through the element.
    """
    regions = [region for box in picture.boxes.values() if (region := _box_band(box)) is not None]
    regions += [
        TextRegion(padded(label), (element.alias,))
        for element in picture.elements.values()
        if (label := text_extent(element.words)) is not None and not element.extent.encloses(label)
    ]
    regions += [
        TextRegion(padded(label), relation.ends)
        for relation in picture.relations
        if (label := text_extent(relation.words)) is not None
    ]
    regions += [TextRegion(padded(text), ()) for words in around if (text := text_extent(words)) is not None]
    return tuple(regions)


def runs_through_text(course: Sequence[Point], region: Extent) -> bool:
    """Whether any segment of *course* runs into *region*, more than a graze."""
    interior = region.shrunk_by(_THROUGH_MARGIN)
    return interior is not None and any(
        interior.is_entered_by(course[index], course[index + 1]) for index in range(len(course) - 1)
    )


def texts_crossed(course: Sequence[Point], regions: Mapping[str, Extent]) -> tuple[str, ...]:
    """The text regions, by key, that *course* runs through."""
    return tuple(key for key, region in regions.items() if runs_through_text(course, region))
