"""The lines a picture keeps as they are drawn once some of its shapes have moved.

A picture taken over by a layout keeps the lines its renderer drew (owner, 2026-11-25): only the lines
touching what moved are routed again. A line is touched when an element it ends at moved, or the side of
a box it ends at — a box grows round a member moved inside it, and a line onto its other sides is not
touched by that — or when something that moved now lies across the line and did not before: an element
with the clearance kept round it (a line it lay across before, outline and all, runs as drawn), a box
neither of the line's ends is in, a text region carried with its shape. Everything else stays exactly as
drawn, even where it would not be the router's own choice: it is what the reader saw before anything
moved, and a line that crossed a box before still may.

The same rule decides which lines a drag routes again from the lines shown before it, so the canvas and
the composer agree on what a stored layout draws. Mirrored in `tools/gui/src/domain/layout/routing/kept.ts`
and held to it by the `kept` case of `tests/fixtures/layout_geometry/routing.json`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.orthogonal import IN_LINE
from src.domain.diagrams.layout.routing.scene import BUFFER, RoutingScene
from src.domain.diagrams.layout.routing.visibility import grown_outward

#: How far a shape may sit from where it was and still be where it was: a layout writes whole pixels.
SAME_PLACE: Final = 1.0

_SIDES: Final = ("top", "right", "bottom", "left")


@dataclass(frozen=True)
class ShownLine:
    """One line as it is shown: its key, its two ends and the course it runs."""

    key: str
    source: str
    target: str
    course: tuple[Point, ...]


def _same(one: Extent | None, other: Extent) -> bool:
    return one is not None and all(
        abs(a - b) <= SAME_PLACE
        for a, b in zip(
            (one.left, one.top, one.right, one.bottom), (other.left, other.top, other.right, other.bottom), strict=True,
        )
    )


def _moved(before: Mapping[str, Extent], now: Mapping[str, Extent]) -> dict[str, tuple[Extent | None, Extent]]:
    """Each shape or region that is not where it was, with where it was (None where it was not) and is."""
    return {key: (before.get(key), extent) for key, extent in now.items() if not _same(before.get(key), extent)}


def _runs_through(course: Sequence[Point], region: Extent | None) -> bool:
    """Whether some run of *course* passes through the inside of *region*."""
    return region is not None and any(
        region.left < max(a.x, b.x) and min(a.x, b.x) < region.right
        and region.top < max(a.y, b.y) and min(a.y, b.y) < region.bottom
        for a, b in zip(course, course[1:], strict=False)
    )


def _distance_to_side(extent: Extent, side: str, point: Point) -> float:
    if side in ("left", "right"):
        x = extent.left if side == "left" else extent.right
        return abs(point.x - x) + max(extent.top - point.y, 0.0, point.y - extent.bottom)
    y = extent.top if side == "top" else extent.bottom
    return abs(point.y - y) + max(extent.left - point.x, 0.0, point.x - extent.right)


def _still_attached(before: Extent, now: Extent, point: Point) -> bool:
    """Whether the side of a box a line ends at, the one nearest its end, stands where it stood and still
    spans the end."""
    side = min(_SIDES, key=lambda one: _distance_to_side(before, one, point))
    if side in ("left", "right"):
        edge = (before.left, now.left) if side == "left" else (before.right, now.right)
        return abs(edge[0] - edge[1]) <= SAME_PLACE and now.top <= point.y <= now.bottom
    edge = (before.top, now.top) if side == "top" else (before.bottom, now.bottom)
    return abs(edge[0] - edge[1]) <= SAME_PLACE and now.left <= point.x <= now.right


def _onto(end: Point, before: Point, extent: Extent) -> Point:
    """*end*, reached along its last run from *before*, carried on along that run onto *extent*'s border."""
    if abs(end.x - before.x) <= IN_LINE and extent.left <= end.x <= extent.right:
        y = extent.top if end.y < extent.top else extent.bottom if end.y > extent.bottom else end.y
        return Point(end.x, y)
    if abs(end.y - before.y) <= IN_LINE and extent.top <= end.y <= extent.bottom:
        x = extent.left if end.x < extent.left else extent.right if end.x > extent.right else end.x
        return Point(x, end.y)
    return end


def attached(course: Sequence[Point], first: Extent, last: Extent) -> tuple[Point, ...]:
    """*course*, as the renderer drew it between *first* and *last*, with each end run carried onto the
    border of the shape it ends at: a drawn line stops where its decoration begins, and a kept line is
    decorated at the border, as a routed one is."""
    if len(course) < 2:  # noqa: PLR2004 — a line has two ends
        return tuple(course)
    return (_onto(course[0], course[1], first), *course[1:-1], _onto(course[-1], course[-2], last))


def kept_lines(before: RoutingScene, now: RoutingScene, lines: Sequence[ShownLine]) -> frozenset[str]:
    """The keys of *lines*, shown over *before*, that nothing moved in *now* touches."""
    elements = _moved(before.elements, now.elements)
    boxes = _moved(before.boxes, now.boxes)
    text = _moved(before.text, now.text)

    def end_moved(key: str, point: Point) -> bool:
        if key in elements:
            return True
        was, box = boxes.get(key, (None, None))
        return box is not None and (was is None or not _still_attached(was, box, point))

    def crossed(line: ShownLine) -> bool:
        """Whether something that moved lies across *line* now and did not before."""
        own = (line.source, line.target)
        ends = tuple(now.extent_of(end) for end in own)
        regions = [
            *((was, grown_outward(extent, BUFFER)) for key, (was, extent) in elements.items() if key not in own),
            *((was, box) for key, (was, box) in boxes.items()
              if key not in own and not any(box.encloses(end) for end in ends)),
            *text.values(),
        ]
        return any(
            _runs_through(line.course, region) and not _runs_through(line.course, was) for was, region in regions
        )

    return frozenset(
        line.key for line in lines
        if not end_moved(line.source, line.course[0]) and not end_moved(line.target, line.course[-1])
        and not crossed(line)
    )
