"""One relation of a rendered picture: the two shapes it joins, its line, its end marks, its label.

**What the picture knows about direction, and what it does not.** PlantUML names a link's two ends
and draws a decoration at either, both or neither. Which end a relation *starts* from is not in the
picture: `A *-- B` and `B <-- A` each put one mark at one end, and the layout engine is free to
draw a link from its second end to its first. So a relation is read as the pair of ends the
renderer names, with its line turned to run from the first to the second and each mark filed under
the end it sits at. Joining that to the model's source and target belongs to whoever holds the
diagram's connections.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from xml.etree.ElementTree import Element  # the type only; input is parsed by defusedxml

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import DrawnRelation, EndMark
from src.infrastructure.rendering.layout._svg_drawing import (
    OUTLINE_TAGS,
    Unreadable,
    end_mark,
    measured_words,
    path_course,
    tag_of,
)


@dataclass(frozen=True)
class RelationMarkup:
    """The markup one relation is drawn with, told apart the way its reading tells it apart.

    For whoever draws the relation again somewhere else: the group that names it, its own line, the
    decorations at each end — filed under the same end as the reading files their marks — and its text.
    """

    group: Element
    line: Element
    first_marks: tuple[Element, ...]
    second_marks: tuple[Element, ...]
    texts: tuple[Element, ...]


def _end_alias(group_id: str | None, alias_by_group_id: Mapping[str, str]) -> str:
    """The alias of the shape drawn in the group *group_id* names."""
    alias = alias_by_group_id.get(group_id) if group_id is not None else None
    if alias is None:
        raise Unreadable(f"a relation ending at {group_id!r}, which no drawn shape carries")
    return alias


def _end_aliases(group: Element, alias_by_group_id: Mapping[str, str]) -> tuple[str, str]:
    """A link's two ends, each named by the `id` of the group it is drawn in."""
    return (
        _end_alias(group.get("data-entity-1"), alias_by_group_id),
        _end_alias(group.get("data-entity-2"), alias_by_group_id),
    )


def _the_line(group: Element) -> Element:
    """The relation's own line: the one path PlantUML gives an `id`."""
    lines = [child for child in group if tag_of(child) == "path" and child.get("id")]
    if len(lines) != 1:
        raise Unreadable(f"a relation drawn with {len(lines)} lines of its own")
    return lines[0]


def _runs_second_to_first(course: tuple[Point, ...], first: Extent, second: Extent) -> bool:
    """Whether the line was drawn starting at the second end, which the layout engine may do."""
    as_named = first.distance_to(course[0]) + second.distance_to(course[-1])
    turned = second.distance_to(course[0]) + first.distance_to(course[-1])
    return turned < as_named


def _mark_centre(mark: EndMark) -> Point:
    extent = Extent.around(mark.outline)
    if extent is None:
        raise Unreadable("a relation decoration that draws nothing")
    return extent.centre


def read_relation(
    group: Element,
    *,
    alias_by_group_id: Mapping[str, str],
    extent_by_alias: Mapping[str, Extent],
) -> tuple[DrawnRelation, RelationMarkup]:
    """The relation drawn in *group*, and the markup that draws it. Raises `Unreadable`."""
    first, second = _end_aliases(group, alias_by_group_id)
    line_type = group.get("data-link-type")
    if not line_type:
        raise Unreadable("a relation that does not state its line type")

    line = _the_line(group)
    path, course = path_course(line)
    if len(course) < 2:  # noqa: PLR2004 — a line has two ends
        raise Unreadable("a relation whose line is a single point")
    if _runs_second_to_first(course, extent_by_alias[first], extent_by_alias[second]):
        path, course = path[::-1], course[::-1]

    first_marks: list[tuple[EndMark, Element]] = []
    second_marks: list[tuple[EndMark, Element]] = []
    texts: list[Element] = []
    for child in group:
        if child is line:
            continue
        tag = tag_of(child)
        if tag == "text":
            texts.append(child)
        elif tag in OUTLINE_TAGS or tag == "line":
            mark = end_mark(child)
            centre = _mark_centre(mark)
            nearer_first = centre.distance_to(course[0]) <= centre.distance_to(course[-1])
            (first_marks if nearer_first else second_marks).append((mark, child))
        else:
            raise Unreadable(f"a <{tag}> inside a relation")

    drawn = DrawnRelation(
        ends=(first, second),
        line_type=line_type,
        path=path,
        course=course,
        first_marks=tuple(mark for mark, _element in first_marks),
        second_marks=tuple(mark for mark, _element in second_marks),
        words=measured_words(texts),
    )
    markup = RelationMarkup(
        group=group,
        line=line,
        first_marks=tuple(element for _mark, element in first_marks),
        second_marks=tuple(element for _mark, element in second_marks),
        texts=tuple(texts),
    )
    return drawn, markup
