"""Routes one relation around the elements of a diagram, at right angles.

The standard technique of the orthogonal-connector literature, in plain Python and with no library:
candidate lines along every element's edge moved out by the margin and along each port's stub; their
crossings are the grid; a search over it costs length, plus a penalty for each bend and for each
stretch another route already runs along, so routes keep apart.

The margin is `STUB`, the same constant the invariants are stated in: a route found here leaves its
element by exactly the stub the checks ask for. One constant, or router and checker disagree.

Built for a diagram of a few hundred elements. Two ports that complete to a sound, clear course are
joined by it without a search. A search is confined to a window around the two ends and widened to
the whole diagram only when the window holds no way through; it commits to a promising way rather
than proving it the cheapest; and "is this stretch inside an element" is answered from a coarse
index rather than by asking every element.
"""

from __future__ import annotations

import heapq
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass

from src.domain.diagrams.layout.attachment import leaves_outward
from src.domain.diagrams.layout.geometry import Extent, Point, course_length
from src.domain.diagrams.layout.layout_block import Port
from src.domain.diagrams.layout.orthogonal import OUTWARD, STUB, completed_course, leaves_level, port_point

#: What one bend costs, in pixels of length a route would rather run than turn.
_BEND = 40.0

#: What running along a stretch another route already uses costs, per stretch.
_SHARED = 60.0

#: How many bends a route that cannot run plainly is assumed to need, when sides are compared.
_DETOUR_BENDS = 4

#: How much the distance still to go is over-weighted in the search. Above 1 the search commits to
#: a promising way instead of proving it the very cheapest; what it finds costs at most this much more.
_EAGERNESS = 1.5

#: How far around the two ends a route is first looked for.
_WINDOW = 180.0

#: How near an element a route that needs no search may pass. Tighter than the margin a searched
#: route keeps: the plain course between two facing ports is preferred to a detour that clears more.
_CLEARANCE = 4.0

#: The side of one cell of the index that answers which elements are near a point.
_CELL = 128.0

_NO_ONE: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Routed:
    """A way found: the points it turns at between its two ports, and what it cost."""

    course: tuple[Point, ...]
    cost: float

    @property
    def bends(self) -> tuple[Point, ...]:
        return self.course[1:-1]


def _without_straight_points(points: Sequence[Point]) -> tuple[Point, ...]:
    kept = [points[0]]
    for index in range(1, len(points) - 1):
        before, here, after = kept[-1], points[index], points[index + 1]
        if not ((before.x == here.x == after.x) or (before.y == here.y == after.y)):
            kept.append(here)
    return (*kept, points[-1])


def _grown(extent: Extent, margin: float) -> Extent:
    return Extent(extent.left - margin, extent.top - margin, extent.right + margin, extent.bottom + margin)


def _steps_from(i: int, j: int) -> tuple[tuple[int, int, bool], ...]:
    """The four neighbouring crossings, each with whether the step to it runs level."""
    return ((i - 1, j, True), (i + 1, j, True), (i, j - 1, False), (i, j + 1, False))


class Router:
    """Finds routes over one arrangement of elements, remembering the ones it was asked to keep apart from."""

    def __init__(self, obstacles: Mapping[str, Extent]) -> None:
        self._obstacles = obstacles
        self._inflated = {key: _grown(extent, STUB) for key, extent in obstacles.items()}
        self._xs = sorted({edge for extent in self._inflated.values() for edge in (extent.left, extent.right)})
        self._ys = sorted({edge for extent in self._inflated.values() for edge in (extent.top, extent.bottom)})
        self._near: dict[tuple[int, int], list[str]] = defaultdict(list)
        for key, extent in self._inflated.items():
            for column in range(int(extent.left // _CELL), int(extent.right // _CELL) + 1):
                for row in range(int(extent.top // _CELL), int(extent.bottom // _CELL) + 1):
                    self._near[(column, row)].append(key)
        #: The stretches committed routes run along: level ones by their y, upright ones by their x.
        self._level_runs: dict[float, list[tuple[float, float]]] = defaultdict(list)
        self._upright_runs: dict[float, list[tuple[float, float]]] = defaultdict(list)

    def _is_inside_an_element(self, x: float, y: float, passable: Container[str]) -> bool:
        for key in self._near.get((int(x // _CELL), int(y // _CELL)), ()):
            extent = self._inflated[key]
            if extent.left < x < extent.right and extent.top < y < extent.bottom and key not in passable:
                return True
        return False

    def _plain_course(
        self, source: Extent, source_port: Port, target: Extent, target_port: Port, passable: Container[str]
    ) -> Routed | None:
        """The course the two ports complete to with no bends stated, where it is sound and clear."""
        course = completed_course(
            port_point(source, source_port), source_port.side, (), port_point(target, target_port), target_port.side
        )
        sound = leaves_outward(source_port.side, course[0], course[1]) and leaves_outward(
            target_port.side, course[-1], course[-2]
        )
        if not sound:
            return None
        for key, extent in self._obstacles.items():
            if key in passable:
                continue
            is_an_end = extent in (source, target)
            kept_clear = extent.shrunk_by(1.0) if is_an_end else _grown(extent, _CLEARANCE)
            if kept_clear is not None and any(
                kept_clear.is_entered_by(start, end) for start, end in zip(course, course[1:], strict=False)
            ):
                return None
        return Routed(course, course_length(course) + _BEND * (len(course) - 2))

    def _shared(self, x: float, y: float, level: bool) -> int:
        runs = self._level_runs.get(y, ()) if level else self._upright_runs.get(x, ())
        along = x if level else y
        return sum(1 for low, high in runs if low < along < high)

    def keep_apart_from(self, course: Sequence[Point]) -> None:
        """Remember *course*, so later routes pay for running along it."""
        for start, end in zip(course, course[1:], strict=False):
            if start.y == end.y:
                self._level_runs[start.y].append((min(start.x, end.x), max(start.x, end.x)))
            elif start.x == end.x:
                self._upright_runs[start.x].append((min(start.y, end.y), max(start.y, end.y)))

    @staticmethod
    def _lines(base: list[float], low: float, high: float, extra: tuple[float, float]) -> list[float]:
        """The candidate lines between *low* and *high*: the elements' edges moved out, and the two stubs."""
        return sorted({*base[bisect_left(base, low) : bisect_right(base, high)], *extra})

    def _search(
        self, start: Point, goal: Point, *, leaves_level_: bool, arrives_level: bool,
        passable: Container[str], window: Extent | None,
    ) -> Routed | None:
        low_x, high_x = (window.left, window.right) if window else (float("-inf"), float("inf"))
        low_y, high_y = (window.top, window.bottom) if window else (float("-inf"), float("inf"))
        xs = self._lines(self._xs, low_x, high_x, (start.x, goal.x))
        ys = self._lines(self._ys, low_y, high_y, (start.y, goal.y))
        column, row = {x: index for index, x in enumerate(xs)}, {y: index for index, y in enumerate(ys)}
        origin = (column[start.x], row[start.y], leaves_level_)
        target = (column[goal.x], row[goal.y])
        cheapest: dict[tuple[int, int, bool], float] = {origin: 0.0}
        came_from: dict[tuple[int, int, bool], tuple[int, int, bool] | None] = {origin: None}
        # Among equally promising states the one that has come furthest goes first: a tie broken the
        # other way explores every route of one length before finishing any.
        frontier: list[tuple[float, float, tuple[int, int, bool]]] = [(0.0, 0.0, origin)]
        while frontier:
            _estimate, behind, state = heapq.heappop(frontier)
            cost = -behind
            i, j, level = state
            if (i, j) == target:
                return Routed(_without_straight_points(self._walked_back(state, came_from, xs, ys)), cost)
            if cost > cheapest.get(state, float("inf")):
                continue
            x, y = xs[i], ys[j]
            for next_i, next_j, next_level in _steps_from(i, j):
                if not (0 <= next_i < len(xs) and 0 <= next_j < len(ys)):
                    continue
                next_x, next_y = xs[next_i], ys[next_j]
                middle_x, middle_y = (x + next_x) / 2, (y + next_y) / 2
                if self._is_inside_an_element(middle_x, middle_y, passable):
                    continue
                step = abs(next_x - x) + abs(next_y - y)
                step += _BEND if next_level != level else 0.0
                step += _SHARED * self._shared(middle_x, middle_y, next_level)
                if (next_i, next_j) == target and next_level != arrives_level:
                    step += _BEND
                reached = (next_i, next_j, next_level)
                if cost + step < cheapest.get(reached, float("inf")):
                    cheapest[reached] = cost + step
                    came_from[reached] = state
                    remaining = abs(goal.x - next_x) + abs(goal.y - next_y)
                    heapq.heappush(frontier, (cost + step + _EAGERNESS * remaining, -(cost + step), reached))
        return None

    @staticmethod
    def _walked_back(
        state: tuple[int, int, bool] | None,
        came_from: Mapping[tuple[int, int, bool], tuple[int, int, bool] | None],
        xs: Sequence[float], ys: Sequence[float],
    ) -> list[Point]:
        points: list[Point] = []
        while state is not None:
            points.append(Point(xs[state[0]], ys[state[1]]))
            state = came_from[state]
        return points[::-1]

    def estimate(
        self, source: Extent, source_port: Port, target: Extent, target_port: Port,
        *, passable: Container[str] = _NO_ONE,
    ) -> float:
        """Roughly what joining two ports costs, without searching: for choosing between sides.

        The plain course where it is sound and clear; otherwise the distance and a detour's bends.
        """
        plain = self._plain_course(source, source_port, target, target_port, passable)
        if plain is not None:
            return plain.cost
        start, end = port_point(source, source_port), port_point(target, target_port)
        return abs(end.x - start.x) + abs(end.y - start.y) + _DETOUR_BENDS * _BEND

    def route(
        self, source: Extent, source_port: Port, target: Extent, target_port: Port,
        *, passable: Container[str] = _NO_ONE,
    ) -> Routed | None:
        """The cheapest way from one port to the other around every element not *passable*, or None.

        *passable* names elements a route may cross: those one of its ends is drawn inside.
        """
        if (plain := self._plain_course(source, source_port, target, target_port, passable)) is not None:
            return plain
        start, end = port_point(source, source_port), port_point(target, target_port)
        out, back = OUTWARD[source_port.side], OUTWARD[target_port.side]
        start_stub = Point(start.x + out[0] * STUB, start.y + out[1] * STUB)
        end_stub = Point(end.x + back[0] * STUB, end.y + back[1] * STUB)
        if self._is_inside_an_element(start_stub.x, start_stub.y, passable) or self._is_inside_an_element(
            end_stub.x, end_stub.y, passable
        ):
            return None  # an element stands within a stub of the port: there is nowhere to leave to
        window = Extent(
            min(source.left, target.left) - _WINDOW, min(source.top, target.top) - _WINDOW,
            max(source.right, target.right) + _WINDOW, max(source.bottom, target.bottom) + _WINDOW,
        )
        for within in (window, None):
            found = self._search(
                start_stub, end_stub, leaves_level_=leaves_level(source_port.side),
                arrives_level=leaves_level(target_port.side), passable=passable, window=within,
            )
            if found is not None:
                course = _without_straight_points((start, *found.course, end))
                return Routed(course, found.cost)
        return None
