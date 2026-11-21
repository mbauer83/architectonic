"""Spans along lines, asked what lies near a run: the routes found so far, box borders, stubs."""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from collections import defaultdict
from collections.abc import Sequence

from src.domain.diagrams.layout.geometry import Point
from src.domain.diagrams.layout.route_quality import LINE_CLEARANCE

#: How much two spans must share to count as running along each other.
_SHARED = 1.0


class Lines:
    """Spans along lines, level ones by their y and upright ones by their x, asked what lies near a run."""

    def __init__(self) -> None:
        self.level: dict[float, list[tuple[float, float]]] = defaultdict(list)
        self.upright: dict[float, list[tuple[float, float]]] = defaultdict(list)
        self._level_at: list[float] = []
        self._upright_at: list[float] = []

    def add(self, a: Point, b: Point) -> None:
        if a.y == b.y and a.x != b.x:
            if a.y not in self.level:
                insort(self._level_at, a.y)
            self.level[a.y].append((min(a.x, b.x), max(a.x, b.x)))
        elif a.x == b.x and a.y != b.y:
            if a.x not in self.upright:
                insort(self._upright_at, a.x)
            self.upright[a.x].append((min(a.y, b.y), max(a.y, b.y)))

    def near(self, a: Point, b: Point, within: float) -> int:
        """How many spans run along the run a–b closer than *within*, sharing some of its stretch."""
        level = a.y == b.y
        at = a.y if level else a.x
        positions = self._level_at if level else self._upright_at
        first = bisect_left(positions, at - within + 1e-9)
        last = bisect_right(positions, at + within - 1e-9)
        return self._sharing(a, b, positions[first:last])

    def between(self, a: Point, b: Point, least: float, most: float) -> int:
        """How many spans lie across the run a–b's line from *least* to *most*, sharing its stretch."""
        positions = self._level_at if a.y == b.y else self._upright_at
        return self._sharing(a, b, positions[bisect_left(positions, least) : bisect_right(positions, most)])

    def spans_near(self, a: Point, b: Point, within: float) -> list[tuple[float, float, float]]:
        """The spans on lines closer than *within* to the run a–b's, as (line, low, high)."""
        level = a.y == b.y
        at = a.y if level else a.x
        positions, spans = (self._level_at, self.level) if level else (self._upright_at, self.upright)
        first = bisect_left(positions, at - within + 1e-9)
        last = bisect_right(positions, at + within - 1e-9)
        return [(position, low, high) for position in positions[first:last] for low, high in spans[position]]

    def _sharing(self, a: Point, b: Point, positions: Sequence[float]) -> int:
        """How many spans on the lines at *positions* share more than `_SHARED` of the run a–b's stretch."""
        level = a.y == b.y
        low, high = (min(a.x, b.x), max(a.x, b.x)) if level else (min(a.y, b.y), max(a.y, b.y))
        spans = self.level if level else self.upright
        count = 0
        for position in positions:
            for span_low, span_high in spans[position]:
                if (high if high < span_high else span_high) - (low if low > span_low else span_low) > _SHARED:
                    count += 1
        return count

    def along(self, a: Point, b: Point) -> bool:
        """Whether the run a–b runs along a span closer than the clearance."""
        return self.near(a, b, LINE_CLEARANCE) > 0


class Stubs:
    """Every connector's stubs, by connector: a run goes along none but its own connector's."""

    def __init__(self) -> None:
        self._lines = Lines()
        self._owners: dict[tuple[bool, float, float, float], set[str]] = defaultdict(set)

    def add(self, a: Point, b: Point, owner: str) -> None:
        self._lines.add(a, b)
        level = a.y == b.y
        at, low, high = (a.y, min(a.x, b.x), max(a.x, b.x)) if level else (a.x, min(a.y, b.y), max(a.y, b.y))
        self._owners[(level, at, low, high)].add(owner)

    def along(self, a: Point, b: Point, owner: str) -> bool:
        """Whether the run a–b goes along a stub of a connector other than *owner*'s."""
        level = a.y == b.y
        low, high = (min(a.x, b.x), max(a.x, b.x)) if level else (min(a.y, b.y), max(a.y, b.y))
        return any(
            self._owners[(level, line, span_low, span_high)] - {owner}
            for line, span_low, span_high in self._lines.spans_near(a, b, LINE_CLEARANCE)
            if min(high, span_high) - max(low, span_low) > _SHARED
        )
