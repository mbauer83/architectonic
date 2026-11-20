"""The course a stated route runs: from its port, through its bends, to its port, every segment upright or level.

A route states little — a side and a fraction at each end, and the bends an author or the router
placed. What is drawn is its **completion**: the elbows that join those points at right angles, so a
relation leaves and enters perpendicular to the side it attaches on. One rule, applied by everything
that asks where a route runs — the composer that draws it, the checks that judge it, the repair that
keeps it attached — and mirrored in TypeScript (`tools/gui/src/domain/layout/orthogonal.ts`) from the
fixtures both are tested against (`tests/fixtures/layout_geometry/`).

Arithmetic the two languages agree on: sums, halves and comparisons for where a course turns.
Rounding is `half_up`, never the language's own, which the two round differently.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from src.domain.diagrams.layout.geometry import Extent, Point, course_length
from src.domain.diagrams.layout.layout_block import Port, Route, Side

#: How far a relation runs straight out of its element before it may turn: the router's margin.
STUB = 12.0

#: How far two points may sit off one line and still count as on it.
IN_LINE = 0.5

#: A segment has two ends; a course of no more has nothing in the middle to drop.
_A_SEGMENT = 2

#: Which way each side faces.
OUTWARD: Mapping[Side, tuple[int, int]] = {
    Side.TOP: (0, -1), Side.RIGHT: (1, 0), Side.BOTTOM: (0, 1), Side.LEFT: (-1, 0),
}


def half_up(value: float) -> int:
    """*value* to the nearest whole number, a half going up — the one rounding both languages share."""
    return math.floor(value + 0.5)


def leaves_level(side: Side) -> bool:
    """Whether a relation attached on *side* leaves it horizontally."""
    return side in (Side.LEFT, Side.RIGHT)


def port_point(extent: Extent, port: Port) -> Point:
    """Where *port* lies on *extent*'s border: along a side from its top or its left."""
    along_x = extent.left + port.at * extent.width
    along_y = extent.top + port.at * extent.height
    return {
        Side.TOP: Point(along_x, extent.top),
        Side.BOTTOM: Point(along_x, extent.bottom),
        Side.LEFT: Point(extent.left, along_y),
        Side.RIGHT: Point(extent.right, along_y),
    }[port.side]


def _through_bends(start: Point, bends: Sequence[Point], level: bool) -> tuple[list[Point], bool]:
    """The course from *start* through each bend, an elbow added wherever two do not line up.

    Answers the course so far and whether it is travelling level when it reaches the last bend.
    """
    course = [start]
    for bend in bends:
        last = course[-1]
        if abs(bend.x - last.x) > IN_LINE and abs(bend.y - last.y) > IN_LINE:
            course.append(Point(bend.x, last.y) if level else Point(last.x, bend.y))
        level = abs(bend.y - course[-1].y) <= IN_LINE
        course.append(bend)
    return course, level


def _joined_to(course: list[Point], level: bool, end: Point, arrives_level: bool) -> list[Point]:
    """*course* carried on to *end*, arriving in the direction its side needs.

    Travelling as it must arrive and not in line: a Z through the midpoint. Travelling the other
    way: an L. In line: straight.
    """
    last = course[-1]
    in_line = abs(last.y - end.y) <= IN_LINE if arrives_level else abs(last.x - end.x) <= IN_LINE
    if in_line:
        return [*course, end]
    if level != arrives_level:
        return [*course, Point(last.x, end.y) if arrives_level else Point(end.x, last.y), end]
    if arrives_level:
        middle = (last.x + end.x) / 2
        return [*course, Point(middle, last.y), Point(middle, end.y), end]
    middle = (last.y + end.y) / 2
    return [*course, Point(last.x, middle), Point(end.x, middle), end]


def _without_idle_points(course: Sequence[Point]) -> tuple[Point, ...]:
    """*course* without the points that turn nothing: a repeat, or one passed in the middle of a straight run.

    A point the course turns back at is kept: a spur is part of what was stated, and of what is judged.
    """
    if len(course) <= _A_SEGMENT:
        return tuple(course)
    kept = [course[0]]
    for index in range(1, len(course) - 1):
        before, here, after = kept[-1], course[index], course[index + 1]
        repeats = abs(before.x - here.x) < IN_LINE and abs(before.y - here.y) < IN_LINE
        upright = abs(before.x - here.x) < IN_LINE and abs(here.x - after.x) < IN_LINE
        level = abs(before.y - here.y) < IN_LINE and abs(here.y - after.y) < IN_LINE
        passed_upright = upright and (here.y - before.y) * (after.y - here.y) >= 0
        passed_level = level and (here.x - before.x) * (after.x - here.x) >= 0
        if not (repeats or passed_upright or passed_level):
            kept.append(here)
    return (*kept, course[-1])


def completed_course(
    start: Point, source_side: Side, bends: Sequence[Point], end: Point, target_side: Side
) -> tuple[Point, ...]:
    """The orthogonal course from *start* through *bends* to *end*, leaving and arriving by its sides."""
    course, level = _through_bends(start, bends, leaves_level(source_side))
    return _without_idle_points(_joined_to(course, level, end, leaves_level(target_side)))


def _stated_end(extent: Extent | None, port: Port | None) -> tuple[Point, Side] | None:
    return (port_point(extent, port), port.side) if extent is not None and port is not None else None


def stated_course(route: Route, source: Extent | None, target: Extent | None) -> tuple[Point, ...]:
    """Where *route* runs as far as it says: completed between two stated ends, else from the one it states.

    An end whose port is unstated, or whose element's extent is not known, is the router's: the
    course stops at the last bend before it. What is returned may be a single point, or nothing.
    """
    bends = [Point(x, y) for x, y in route.via]
    start, end = _stated_end(source, route.source), _stated_end(target, route.target)
    if start is not None and end is not None:
        return completed_course(start[0], start[1], bends, end[0], end[1])
    if start is not None:
        return _without_idle_points(_through_bends(start[0], bends, leaves_level(start[1]))[0])
    if end is not None:
        return _without_idle_points(_through_bends(end[0], bends[::-1], leaves_level(end[1]))[0])[::-1]
    return tuple(bends)


def course_of(route: Route, source: Extent, target: Extent) -> tuple[Point, ...] | None:
    """Where *route* runs between two elements, or None where it leaves a port for the router to decide."""
    if route.source is None or route.target is None:
        return None
    return stated_course(route, source, target)


def point_along(course: Sequence[Point], at: float) -> Point:
    """The point a fraction *at* of the way along *course*."""
    goal, walked = at * course_length(course), 0.0
    for index in range(len(course) - 1):
        start, end = course[index], course[index + 1]
        length = start.distance_to(end)
        if length > 0 and walked + length >= goal:
            share = (goal - walked) / length
            return Point(start.x + share * (end.x - start.x), start.y + share * (end.y - start.y))
        walked += length
    return course[-1]


def fraction_along(course: Sequence[Point], point: Point) -> float:
    """How far along *course*, from 0 to 1, the place nearest *point* lies."""
    nearest, reached, walked = math.inf, 0.0, 0.0
    for index in range(len(course) - 1):
        start, end = course[index], course[index + 1]
        length = start.distance_to(end)
        if length == 0:
            continue
        share = ((point.x - start.x) * (end.x - start.x) + (point.y - start.y) * (end.y - start.y)) / length**2
        share = max(0.0, min(1.0, share))
        foot = Point(start.x + share * (end.x - start.x), start.y + share * (end.y - start.y))
        if (distance := foot.distance_to(point)) < nearest:
            nearest, reached = distance, walked + share * length
        walked += length
    return reached / walked if walked > 0 else 0.0
