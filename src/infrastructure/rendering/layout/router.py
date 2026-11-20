"""Routes one relation around the elements of a diagram, at right angles, so a reader can follow it.

The standard technique of the orthogonal-connector literature, in plain Python and with no library:
candidate lines along every element's edge moved out by the margin, along each text region and box
border kept clear of, and along each end's run; their crossings are the grid; a search over it costs
length plus a penalty for each bend.

What a route keeps, beside going round the elements it does not join (I5):

* hard: no text — a text region is never entered (`text_clearance`); a straight run into each end
  where it bends, so no bend sits at a decoration; no run along a box border or another route —
  routes cross, they never merge (`route_quality`);
* soft: bends cost, and a jog the route did not need is straightened out where what is left still
  keeps the hard rules. A necessary jog stays.

The margin is `STUB`, the same constant the invariants are stated in. Built for a diagram of a few
hundred elements: two ports that complete to a clear course are joined by it without a search; a
search is confined to a window around the two ends and widened only when the window holds no way; it
commits to a promising way rather than proving it the very cheapest.
"""

from __future__ import annotations

import heapq
from bisect import bisect_left, bisect_right, insort
from collections import defaultdict
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from src.domain.diagrams.layout.attachment import leaves_outward
from src.domain.diagrams.layout.geometry import Extent, Point, course_length
from src.domain.diagrams.layout.layout_block import Port
from src.domain.diagrams.layout.orthogonal import OUTWARD, STUB, completed_course, leaves_level, port_point
from src.domain.diagrams.layout.route_quality import END_RUN, LINE_CLEARANCE, bends_at_ends, kinks
from src.domain.diagrams.layout.text_clearance import runs_through_text, texts_crossed
from src.infrastructure.rendering.layout._parallel_lines import ParallelLines

#: What one bend costs, in pixels of length a route would rather run than turn.
_BEND = 40.0

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

#: How far off a border, or off text, a candidate line runs.
_OFF_A_LINE = 8.0

#: How far beside a route a later route is offered a line of its own.
_BESIDE = 1.5 * LINE_CLEARANCE

#: The prefix that keeps a text region's key apart from an element's in the index.
_TEXT = "text:"

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


class Leniency(Enum):
    """How much of the hard rules a search may set aside, tried in this order by a caller that found no way.

    Every rule is kept first, from every side. Then a decorated end may be reached by a stub rather
    than a full run; then a route may also run along a route already drawn. Each is better than the
    last resort, a line through an element or a text.
    """

    STRICT = 1
    SHORT_RUNS = 2
    BESIDE_ROUTES = 3


@dataclass(frozen=True)
class Surroundings:
    """What a route keeps clear of besides the elements: text, and the borders of boxes and elements.

    *text* is every text region, already padded: no route enters one, whatever its ends. *borders* are
    the outlines a route may cross but never run along.
    """

    text: Mapping[str, Extent] = field(default_factory=dict)
    borders: Sequence[Extent] = ()


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


def _out_by(point: Point, port: Port, distance: float) -> Point:
    out = OUTWARD[port.side]
    return Point(point.x + out[0] * distance, point.y + out[1] * distance)


class Router:
    """Finds routes over one arrangement of elements, keeping each clear of the ones already found."""

    def __init__(self, obstacles: Mapping[str, Extent], around: Surroundings | None = None) -> None:
        around = around or Surroundings()
        self._obstacles, self._text = obstacles, around.text
        self._inflated = {key: _grown(extent, STUB) for key, extent in obstacles.items()}
        # Text keeps its own padding: grown again, a title band would reach outside its box.
        self._inflated.update({_TEXT + key: extent for key, extent in around.text.items()})
        self._borders, self._routes = ParallelLines(around.borders), ParallelLines()
        #: Set for one search, where no way keeps clear of the routes already drawn: see `route`.
        self._beside_routes = False
        #: Set for one search: the boxes that route may not enter. See `route`.
        self._walls: Sequence[Extent] = ()
        every = [
            *self._inflated.values(), *(_grown(extent, _OFF_A_LINE) for extent in around.text.values()),
            *(_grown(extent, _OFF_A_LINE) for extent in around.borders),
        ]
        self._xs = sorted({edge for extent in every for edge in (extent.left, extent.right)})
        self._ys = sorted({edge for extent in every for edge in (extent.top, extent.bottom)})
        self._near: dict[tuple[int, int], list[str]] = defaultdict(list)
        for key, extent in self._inflated.items():
            for column in range(int(extent.left // _CELL), int(extent.right // _CELL) + 1):
                for row in range(int(extent.top // _CELL), int(extent.bottom // _CELL) + 1):
                    self._near[(column, row)].append(key)

    def keep_apart_from(self, course: Sequence[Point]) -> None:
        """Remember *course*, so no later route runs along it, and offer the lines beside it instead.

        The grid has one candidate line down a corridor between two elements; once a route takes it,
        the next one through that corridor needs a line of its own, a clearance and a half away.
        """
        self._routes.add_course(course)
        for start, end in zip(course, course[1:], strict=False):
            lines, at = (self._ys, start.y) if start.y == end.y else (self._xs, start.x)
            for beside in (at - _BESIDE, at + _BESIDE):
                if beside not in lines:
                    insort(lines, beside)

    def forget(self, course: Sequence[Point]) -> None:
        """Stop keeping apart from *course*, for a route that is about to be found again."""
        self._routes.remove_course(course)

    def _alongside(self, start: Point, end: Point) -> bool:
        """Whether a run lies along a border, or along a route already drawn unless that is allowed now."""
        return self._borders.runs_along(start, end) or (
            not self._beside_routes and self._routes.runs_along(start, end)
        )

    def _is_inside_an_element(self, x: float, y: float, passable: Container[str]) -> bool:
        """Whether a point lies inside an element not *passable*, grown by the margin, or inside text."""
        for key in self._near.get((int(x // _CELL), int(y // _CELL)), ()):
            extent = self._inflated[key]
            if extent.left < x < extent.right and extent.top < y < extent.bottom and key not in passable:
                return True
        return any(wall.left < x < wall.right and wall.top < y < wall.bottom for wall in self._walls)

    def is_clear(
        self, course: Sequence[Point], ends: tuple[Extent, Extent], passable: Container[str],
        decorated: tuple[bool, bool] = (True, True),
    ) -> bool:
        """Whether *course* keeps every hard rule: clear of elements, text, borders and routes, no bend at an end.

        A jog is not refused here: it is soft, and a necessary one stays.
        """
        runs = list(zip(course, course[1:], strict=False))
        for key, extent in self._obstacles.items():
            if key in passable:
                continue
            kept_clear = extent.shrunk_by(1.0) if extent in ends else _grown(extent, _CLEARANCE)
            if kept_clear is not None and any(kept_clear.is_entered_by(start, end) for start, end in runs):
                return False
        for wall in self._walls:
            inside = wall.shrunk_by(1.0)
            if inside is not None and any(inside.is_entered_by(start, end) for start, end in runs):
                return False
        return not (
            texts_crossed(course, self._text) or any(
                self._alongside(start, end) for start, end in zip(course, course[1:], strict=False)
            )
            or bends_at_ends(course, decorated)
        )

    def _is_blocked(self, here: Point, there: Point, passable: Container[str]) -> bool:
        """Whether one step of a search may not be taken: it ends in or passes through what it keeps out of.

        The middle and the far end are asked of the elements and boxes, whose grid lines lie outside
        them; text is asked of the whole step, since a band is thinner than the step across it.
        """
        return (
            self._is_inside_an_element((here.x + there.x) / 2, (here.y + there.y) / 2, passable)
            or self._is_inside_an_element(there.x, there.y, passable)
            or self._alongside(here, there)
            or any(runs_through_text((here, there), region) for region in self._text.values())
        )

    def _may_leave(self, port: Point, stub: Point, passable: Container[str]) -> bool:
        """Whether the straight run out of a port to *stub* stays clear of other elements, text and lines."""
        return (
            not self._is_inside_an_element(stub.x, stub.y, passable)
            and not texts_crossed((port, stub), self._text)
            and not self._alongside(port, stub)
        )

    def _plain_course(
        self, source: Extent, source_port: Port, target: Extent, target_port: Port, passable: Container[str],
        decorated: tuple[bool, bool] = (True, True),
    ) -> Routed | None:
        """The course the two ports complete to with no bends stated, where it is sound and clear."""
        course = completed_course(
            port_point(source, source_port), source_port.side, (), port_point(target, target_port), target_port.side
        )
        sound = leaves_outward(source_port.side, course[0], course[1]) and leaves_outward(
            target_port.side, course[-1], course[-2]
        )
        if not sound or not self.is_clear(course, (source, target), passable, decorated):
            return None
        return Routed(course, course_length(course) + _BEND * (len(course) - 2))

    @staticmethod
    def _lines(base: list[float], low: float, high: float, extra: Sequence[float]) -> list[float]:
        """The candidate lines between *low* and *high*, the two ends' runs, and the lines off this search's walls."""
        return sorted({*base[bisect_left(base, low) : bisect_right(base, high)], *extra})

    def _search(
        self, start: Point, goal: Point, *, leaves_level_: bool, arrives_level: bool,
        passable: Container[str], window: Extent | None,
    ) -> Routed | None:
        low_x, high_x = (window.left, window.right) if window else (float("-inf"), float("inf"))
        low_y, high_y = (window.top, window.bottom) if window else (float("-inf"), float("inf"))
        off_walls = [_grown(wall, _OFF_A_LINE) for wall in self._walls]
        xs = self._lines(self._xs, low_x, high_x, (start.x, goal.x, *(e for w in off_walls for e in (w.left, w.right))))
        ys = self._lines(self._ys, low_y, high_y, (start.y, goal.y, *(e for w in off_walls for e in (w.top, w.bottom))))
        column, row = {x: index for index, x in enumerate(xs)}, {y: index for index, y in enumerate(ys)}
        origin = (column[start.x], row[start.y], leaves_level_)
        target = (column[goal.x], row[goal.y])
        cheapest: dict[tuple[int, int, bool], float] = {origin: 0.0}
        came_from: dict[tuple[int, int, bool], tuple[int, int, bool] | None] = {origin: None}
        # Among equally promising states the one that has come furthest goes first.
        frontier: list[tuple[float, float, tuple[int, int, bool]]] = [(0.0, 0.0, origin)]
        while frontier:
            _estimate, behind, state = heapq.heappop(frontier)
            cost = -behind
            i, j, level = state
            if (i, j) == target:
                return Routed(_without_straight_points(self._walked_back(state, came_from, xs, ys)), cost)
            if cost > cheapest.get(state, float("inf")):
                continue
            here = Point(xs[i], ys[j])
            for next_i, next_j, next_level in _steps_from(i, j):
                if not (0 <= next_i < len(xs) and 0 <= next_j < len(ys)):
                    continue
                there = Point(xs[next_i], ys[next_j])
                if self._is_blocked(here, there, passable):
                    continue
                step = abs(there.x - here.x) + abs(there.y - here.y) + (_BEND if next_level != level else 0.0)
                if (next_i, next_j) == target and next_level != arrives_level:
                    step += _BEND
                reached = (next_i, next_j, next_level)
                if cost + step < cheapest.get(reached, float("inf")):
                    cheapest[reached] = cost + step
                    came_from[reached] = state
                    remaining = abs(goal.x - there.x) + abs(goal.y - there.y)
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

    def _straightened(
        self, course: tuple[Point, ...], ends: tuple[Extent, Extent], passable: Container[str],
        decorated: tuple[bool, bool],
    ) -> tuple[Point, ...]:
        """*course* with each jog shorter than a readable segment taken out, where what is left is clear.

        A jog is a short segment between two runs in one direction; moving either run onto the other's
        line removes it. The ends' own runs are never moved: they leave their ports.
        """
        for index in kinks(course):
            for moved in (index + 1, index - 1):
                if not 1 <= moved <= len(course) - 3:  # noqa: PLR2004 — a run between two bends
                    continue
                trial = list(course)
                level = course[moved].y == course[moved + 1].y
                keep = course[index if moved == index + 1 else index + 1]
                for at in (moved, moved + 1):
                    trial[at] = Point(trial[at].x, keep.y) if level else Point(keep.x, trial[at].y)
                candidate = _without_straight_points(trial)
                if self.is_clear(candidate, ends, passable, decorated):
                    return self._straightened(candidate, ends, passable, decorated)
        return course

    def estimate(
        self, source: Extent, source_port: Port, target: Extent, target_port: Port,
        *, passable: Container[str] = _NO_ONE,
    ) -> float:
        """Roughly what joining two ports costs, without searching: for choosing between sides."""
        plain = self._plain_course(source, source_port, target, target_port, passable)
        if plain is not None:
            return plain.cost
        start, end = port_point(source, source_port), port_point(target, target_port)
        return abs(end.x - start.x) + abs(end.y - start.y) + _DETOUR_BENDS * _BEND

    def route(
        self, source: Extent, source_port: Port, target: Extent, target_port: Port,
        *, passable: Container[str] = _NO_ONE, decorated: tuple[bool, bool] = (True, True),
        leniency: Leniency = Leniency.STRICT, walls: Sequence[Extent] = (),
    ) -> Routed | None:
        """The cheapest way from one port to the other that keeps every rule *leniency* keeps, or None.

        *walls* are the boxes the route may not enter: a box holds neither of its ends, or is an end, so
        a line reaching it arrives at its border from outside and never through what it holds.
        """
        self._beside_routes, self._walls = leniency is Leniency.BESIDE_ROUTES, walls
        try:
            return self._route(source, source_port, target, target_port, passable, decorated, leniency)
        finally:
            self._beside_routes, self._walls = False, ()

    def _route(
        self, source: Extent, source_port: Port, target: Extent, target_port: Port,
        passable: Container[str], decorated: tuple[bool, bool], leniency: Leniency,
    ) -> Routed | None:
        """The route itself.

        *passable* names elements a route may cross: those one of its ends is drawn inside. A route
        leaves and arrives by a straight run of `END_RUN` at a decorated end where there is room for one,
        else by a stub; *decorated* says which ends carry a decoration.
        """
        plain = self._plain_course(
            source, source_port, target, target_port, passable,
            decorated if leniency is Leniency.STRICT else (False, False),
        )
        if plain is not None:
            return plain
        start, end = port_point(source, source_port), port_point(target, target_port)
        windows = [
            Extent(
                min(source.left, target.left) - reach, min(source.top, target.top) - reach,
                max(source.right, target.right) + reach, max(source.bottom, target.bottom) + reach,
            )
            for reach in (_WINDOW, 3 * _WINDOW)
        ]
        wanted = tuple(END_RUN if marked else STUB for marked in decorated)
        for runs in (wanted,) if leniency is Leniency.STRICT else (wanted, (STUB, STUB)):
            start_stub, end_stub = _out_by(start, source_port, runs[0]), _out_by(end, target_port, runs[1])
            if not (self._may_leave(start, start_stub, passable) and self._may_leave(end, end_stub, passable)):
                continue  # an element or text stands within this run of a port: there is nowhere to leave to
            for within in (*windows, None):
                found = self._search(
                    start_stub, end_stub, leaves_level_=leaves_level(source_port.side),
                    arrives_level=leaves_level(target_port.side), passable=passable, window=within,
                )
                if found is not None:
                    course = self._straightened(
                        _without_straight_points((start, *found.course, end)), (source, target), passable, decorated
                    )
                    return Routed(course, found.cost)
        return None
