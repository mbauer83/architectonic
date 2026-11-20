"""The lines a route may cross but never run along: box borders, and the routes already drawn.

Kept by position — level lines by their y, upright ones by their x — so asking whether a run lies
alongside any of them is a range lookup on one axis, not a walk over every line. The rule asked is
`route_quality`'s C: closer than `LINE_CLEARANCE` and sharing some length is running along.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from collections import defaultdict
from collections.abc import Iterable, Sequence

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.route_quality import LINE_CLEARANCE

#: How much two spans must share along their length to count as running along each other.
_SHARED_LENGTH = 1.0


class _Lines:
    """Spans along lines of one direction, by the lines' positions."""

    def __init__(self) -> None:
        self._spans: dict[float, list[tuple[float, float]]] = defaultdict(list)
        self._positions: list[float] = []

    def add(self, at: float, low: float, high: float) -> None:
        if at not in self._spans:
            insort(self._positions, at)
        self._spans[at].append((low, high))

    def remove(self, at: float, low: float, high: float) -> None:
        spans = self._spans.get(at, [])
        if (low, high) in spans:
            spans.remove((low, high))

    def alongside(self, at: float, low: float, high: float) -> bool:
        first = bisect_left(self._positions, at - LINE_CLEARANCE + 1e-9)
        last = bisect_right(self._positions, at + LINE_CLEARANCE - 1e-9)
        return any(
            min(high, span_high) - max(low, span_low) > _SHARED_LENGTH
            for position in self._positions[first:last]
            for span_low, span_high in self._spans[position]
        )


def _runs(course: Sequence[Point]) -> Iterable[tuple[bool, float, float, float]]:
    for start, end in zip(course, course[1:], strict=False):
        if start.y == end.y and start.x != end.x:
            yield True, start.y, min(start.x, end.x), max(start.x, end.x)
        elif start.x == end.x and start.y != end.y:
            yield False, start.x, min(start.y, end.y), max(start.y, end.y)


class ParallelLines:
    """Every line a route keeps its distance from when it runs parallel to it."""

    def __init__(self, borders: Sequence[Extent] = ()) -> None:
        self._level, self._upright = _Lines(), _Lines()
        for box in borders:
            for at in (box.top, box.bottom):
                self._level.add(at, box.left, box.right)
            for at in (box.left, box.right):
                self._upright.add(at, box.top, box.bottom)

    def add_course(self, course: Sequence[Point]) -> None:
        for level, at, low, high in _runs(course):
            (self._level if level else self._upright).add(at, low, high)

    def remove_course(self, course: Sequence[Point]) -> None:
        for level, at, low, high in _runs(course):
            (self._level if level else self._upright).remove(at, low, high)

    def runs_along(self, start: Point, end: Point) -> bool:
        """Whether the run from *start* to *end* lies alongside any line kept here."""
        return any(
            (self._level if level else self._upright).alongside(at, low, high)
            for level, at, low, high in _runs((start, end))
        )

    def course_runs_along(self, course: Sequence[Point]) -> bool:
        return any(self.runs_along(start, end) for start, end in zip(course, course[1:], strict=False))
