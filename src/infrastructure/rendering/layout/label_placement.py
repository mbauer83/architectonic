"""Where a relation's label sits when nobody has placed it: beside its route, clear of every element.

A label is anchored to its route — a fraction of the way along, and an offset from that point to the
label's centre — so it rides with the route when the route changes. An author's anchor is kept as
stated; this decides the ones left unstated. Places are tried from the middle of the route outwards,
on either side of the line, and the first whose box lies over no element and no label already placed
is taken. Where every place is taken the middle is used: a label over something is still a label.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.diagrams.layout.geometry import Extent, Point, course_length
from src.domain.diagrams.layout.layout_block import LabelAnchor
from src.domain.diagrams.layout.orthogonal import IN_LINE, half_up, point_along

#: How far along a route a label is tried, the middle first.
_FRACTIONS = (0.5, 0.35, 0.65, 0.25, 0.75, 0.15, 0.85, 0.42, 0.58, 0.3, 0.7, 0.2, 0.8)

#: The room left between a label and the line it labels.
_OFF_THE_LINE = 4.0


def label_box(course: Sequence[Point], anchor: LabelAnchor, size: tuple[float, float]) -> Extent:
    """The rectangle a label of *size* occupies when anchored at *anchor* on *course*."""
    on_route = point_along(course, anchor.at)
    centre = Point(on_route.x + anchor.dx, on_route.y + anchor.dy)
    return Extent(centre.x - size[0] / 2, centre.y - size[1] / 2, centre.x + size[0] / 2, centre.y + size[1] / 2)


def _runs_level_at(course: Sequence[Point], at: float) -> bool:
    """Whether the route is travelling level at the point a fraction *at* along it."""
    goal, walked = at * course_length(course), 0.0
    for start, end in zip(course, course[1:], strict=False):
        length = start.distance_to(end)
        if length > 0 and walked + length >= goal:
            return abs(end.y - start.y) <= IN_LINE
        walked += length
    return True


def _offsets(level: bool, size: tuple[float, float]) -> tuple[tuple[int, int], ...]:
    """Either side of the line: above and below a level run, right and left of an upright one."""
    if level:
        away = half_up(size[1] / 2 + _OFF_THE_LINE)
        return ((0, -away), (0, away))
    away = half_up(size[0] / 2 + _OFF_THE_LINE)
    return ((away, 0), (-away, 0))


def _is_crossed(box: Extent, lines: Sequence[Sequence[Point]]) -> bool:
    inner = box.shrunk_by(1.0)
    return inner is not None and any(
        inner.is_entered_by(start, end) for line in lines for start, end in zip(line, line[1:], strict=False)
    )


def placed_label(
    course: Sequence[Point], size: tuple[float, float], keep_clear_of: Sequence[Extent],
    lines: Sequence[Sequence[Point]] = (),
) -> LabelAnchor:
    """An anchor for a label of *size* on *course* whose box lies over nothing in *keep_clear_of* and
    no line of *lines* runs through: a line never passes through text."""
    candidates = [
        LabelAnchor(at, dx, dy)
        for at in _FRACTIONS
        for dx, dy in _offsets(_runs_level_at(course, at), size)
    ]
    return next(
        (
            anchor for anchor in candidates
            if not any(label_box(course, anchor, size).overlap_with(taken) for taken in keep_clear_of)
            and not _is_crossed(label_box(course, anchor, size), lines)
        ),
        candidates[0],
    )
