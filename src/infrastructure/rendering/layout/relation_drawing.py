"""One relation drawn along the course a layout gives it: its line, its end decorations, its label.

The line is a rounded orthogonal polyline. Its stroke — colour, weight, dashes — is the one PlantUML
drew, and so are the decorations, placed at the new ends by `relation_decorations`. The group keeps
every attribute it had, so whatever identifies a relation on a rendered picture identifies it here.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from xml.etree.ElementTree import Element

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import DrawnRelation
from src.infrastructure.rendering.layout._svg_relations import RelationMarkup
from src.infrastructure.rendering.layout.arrangement import ArrangedRelation, label_extent
from src.infrastructure.rendering.layout.relation_decorations import (
    frame_as_drawn,
    frame_at_end,
    placed_decorations,
    stopping_short,
)
from src.infrastructure.rendering.layout.svg_markup import Motion, moved
from src.infrastructure.rendering.layout.svg_path_data import written_number

#: How round a bend is drawn.
_BEND_RADIUS = 6.0

#: Below this a bend is drawn sharp: there is no room for a curve worth drawing.
_SHARP_BELOW = 0.5

_A_RUN = 2


def _at(point: Point) -> str:
    return f"{written_number(point.x)},{written_number(point.y)}"


def _towards(start: Point, end: Point, distance: float) -> Point:
    length = start.distance_to(end)
    return Point(start.x + (end.x - start.x) / length * distance, start.y + (end.y - start.y) / length * distance)


def rounded_path(course: Sequence[Point]) -> str:
    """The path data of a line through *course* with each bend rounded as far as its two runs allow."""
    written = [f"M{_at(course[0])}"]
    for before, bend, after in zip(course, course[1:], course[2:], strict=False):
        radius = min(_BEND_RADIUS, before.distance_to(bend) / 2, bend.distance_to(after) / 2)
        if radius < _SHARP_BELOW:
            written.append(f"L{_at(bend)}")
            continue
        written.append(f"L{_at(_towards(bend, before, radius))} Q{_at(bend)} {_at(_towards(bend, after, radius))}")
    written.append(f"L{_at(course[-1])}")
    return " ".join(written)


def drawn_relation(
    markup: RelationMarkup, drawn: DrawnRelation, arranged: ArrangedRelation, drawn_ends: tuple[Extent, Extent]
) -> Element:
    """The group that draws one relation along *arranged*'s course.

    *drawn* is the relation as PlantUML drew it and *drawn_ends* where its two ends sat then: the
    frames its decorations were drawn in are taken from those.
    """
    if len(arranged.course) < _A_RUN:
        return copy.deepcopy(markup.group)
    course, backwards = arranged.course, arranged.course[::-1]
    first_as_drawn = frame_as_drawn(drawn.first_marks, drawn.course[::-1], drawn_ends[0])
    second_as_drawn = frame_as_drawn(drawn.second_marks, drawn.course, drawn_ends[1])

    group = Element(markup.group.tag, dict(markup.group.attrib))
    line = copy.deepcopy(markup.line)
    line.set("d", rounded_path(stopping_short(course, first_as_drawn.gap, second_as_drawn.gap)))
    group.append(line)
    group.extend(placed_decorations(markup.first_marks, first_as_drawn, frame_at_end(backwards, first_as_drawn.gap)))
    group.extend(placed_decorations(markup.second_marks, second_as_drawn, frame_at_end(course, second_as_drawn.gap)))

    was = label_extent(drawn.words)
    if was is not None and arranged.label_centre is not None:
        carried = Motion.shift(arranged.label_centre.x - was.centre.x, arranged.label_centre.y - was.centre.y)
        group.extend(moved(text, carried) for text in markup.texts)
    return group
