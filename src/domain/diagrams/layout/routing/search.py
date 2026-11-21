"""A* over the visibility graph, from any of a connector's starts to any of its goals (GD 2009 §4).

A state is a node of the graph and the direction the route travels into it; a step costs its length
and `BEND_PENALTY` where it turns. The estimate is the Manhattan distance to the nearest goal, weighted
by `EAGERNESS`: the route found costs at most that much more than the cheapest, and the search
explores a fraction of the states. Ties are broken by the order states were reached, so both languages
find the same one.

A start is a stub end, travelling outward from its port; a goal is a stub end, entered travelling
towards its port. Reaching a goal in another direction costs the bend into the stub. The search first
looks within a window round its terminals and widens it only when the window holds no way, or only
one through a channel already full.
"""

from __future__ import annotations

import heapq
from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.routing.scene import BEND_PENALTY, CROWDING
from src.domain.diagrams.layout.routing.visibility import FULL, Passage, lines_within

#: The four directions a route travels in, as steps along the grid: east, west, south, north.
DIRECTIONS: tuple[tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))

#: The direction opposite each direction.
REVERSE: tuple[int, ...] = (1, 0, 3, 2)

#: How much the distance still to go is over-weighted. Above 1 the search commits to a promising way
#: rather than proving it the very cheapest; what it finds costs at most this much more.
EAGERNESS = 1.5

#: How far round its terminals a search looks first; then three times as far; then everywhere.
WINDOW = 200.0


@dataclass(frozen=True)
class Terminal:
    """A stub end: where a route starts or finishes, the direction it travels there, and which one it is."""

    point: Point
    direction: int
    tag: int


@dataclass(frozen=True)
class Found:
    """A cheapest route between one start and one goal: its points from stub end to stub end."""

    points: tuple[Point, ...]
    start: int
    goal: int
    cost: float


def _windows(terminals: Sequence[Terminal]) -> list[Extent | None]:
    left = min(terminal.point.x for terminal in terminals)
    top = min(terminal.point.y for terminal in terminals)
    right = max(terminal.point.x for terminal in terminals)
    bottom = max(terminal.point.y for terminal in terminals)
    return [
        Extent(left - reach, top - reach, right + reach, bottom + reach) for reach in (WINDOW, 3 * WINDOW)
    ] + [None]


def _without_straight_points(points: Sequence[Point]) -> tuple[Point, ...]:
    kept = [points[0]]
    for index in range(1, len(points) - 1):
        before, here, after = kept[-1], points[index], points[index + 1]
        if not ((before.x == here.x == after.x) or (before.y == here.y == after.y)):
            kept.append(here)
    return (*kept, points[-1]) if len(points) > 1 else tuple(kept)


def _search_within(
    starts: Sequence[Terminal], goals: Sequence[Terminal], passage: Passage,
    xs: list[float], ys: list[float],
) -> Found | None:
    column = {x: index for index, x in enumerate(xs)}
    row = {y: index for index, y in enumerate(ys)}
    goals_at: dict[tuple[int, int], list[int]] = {}
    for index, goal in enumerate(goals):
        goals_at.setdefault((column[goal.point.x], row[goal.point.y]), []).append(index)

    def estimate(x: float, y: float) -> float:
        return min(abs(goal.point.x - x) + abs(goal.point.y - y) for goal in goals)

    steps: dict[tuple[int, int, int], float | None] = {}

    def step_cost(i: int, j: int, turn: int) -> float | None:
        """What the step from node (i, j) in direction *turn* costs, or None where it is blocked: asked
        once per step, however many states reach its node."""
        key = (i, j, turn)
        if key not in steps:
            next_i, next_j = i + DIRECTIONS[turn][0], j + DIRECTIONS[turn][1]
            if not (0 <= next_i < len(xs) and 0 <= next_j < len(ys)):
                steps[key] = None
            else:
                here, there = Point(xs[i], ys[j]), Point(xs[next_i], ys[next_j])
                if passage.point_blocked(there) or passage.step_blocked(here, there):
                    steps[key] = None
                else:
                    # A run another route already takes costs more: later routes spread over the channels.
                    length = abs(there.x - here.x) + abs(there.y - here.y)
                    steps[key] = length * (1 + CROWDING * passage.crowding(here, there))
        return steps[key]

    best: dict[tuple[int, int, int], float] = {}
    came: dict[tuple[int, int, int], tuple[int, int, int] | None] = {}
    began: dict[tuple[int, int, int], int] = {}
    # f, order, i, j, direction, goal index (-1: an ordinary state; else: finishing at that goal)
    frontier: list[tuple[float, int, int, int, int, int]] = []
    order = 0
    for start in starts:
        state = (column[start.point.x], row[start.point.y], start.direction)
        if state not in best:
            best[state], came[state], began[state] = 0.0, None, start.tag
            heapq.heappush(frontier, (EAGERNESS * estimate(start.point.x, start.point.y), order, *state, -1))
            order += 1
    while frontier:
        f, _order, i, j, last, finishing = heapq.heappop(frontier)
        state = (i, j, last)
        if finishing >= 0:
            return Found(_walked_back(state, came, xs, ys), began[state], goals[finishing].tag, f)
        g = best[state]
        if f > g + EAGERNESS * estimate(xs[i], ys[j]):
            continue  # reached again more cheaply since this entry was made
        for index in goals_at.get((i, j), ()):
            if last == REVERSE[goals[index].direction]:
                continue  # turning back into the stub would run along it
            finish = g + (BEND_PENALTY if last != goals[index].direction else 0.0)
            heapq.heappush(frontier, (finish, order, i, j, last, index))
            order += 1
        for turn in range(4):
            if turn == REVERSE[last]:
                continue
            length = step_cost(i, j, turn)
            if length is None:
                continue
            next_i, next_j = i + DIRECTIONS[turn][0], j + DIRECTIONS[turn][1]
            there = Point(xs[next_i], ys[next_j])
            reached = (next_i, next_j, turn)
            cost = g + length + (BEND_PENALTY if turn != last else 0.0)
            if cost < best.get(reached, float("inf")):
                best[reached], came[reached], began[reached] = cost, state, began[state]
                heapq.heappush(frontier, (cost + EAGERNESS * estimate(there.x, there.y), order, *reached, -1))
                order += 1
    return None


def _walked_back(
    state: tuple[int, int, int] | None, came: dict[tuple[int, int, int], tuple[int, int, int] | None],
    xs: list[float], ys: list[float],
) -> tuple[Point, ...]:
    points: list[Point] = []
    while state is not None:
        points.append(Point(xs[state[0]], ys[state[1]]))
        state = came[state]
    return _without_straight_points(points[::-1])


def search(
    starts: Sequence[Terminal], goals: Sequence[Terminal], passage: Passage,
    xs: Sequence[float], ys: Sequence[float],
) -> Found | None:
    """The cheapest route from any start to any goal over the lines *xs* and *ys*, or None."""
    terminals = [*starts, *goals]
    best: Found | None = None
    for window in _windows(terminals):
        if window is None and best is not None:
            break  # the whole diagram is searched only where no window held any way at all
        low_x, high_x = (window.left, window.right) if window else (float("-inf"), float("inf"))
        low_y, high_y = (window.top, window.bottom) if window else (float("-inf"), float("inf"))
        found = _search_within(
            starts, goals, passage,
            lines_within(xs, low_x, high_x, (terminal.point.x for terminal in terminals)),
            lines_within(ys, low_y, high_y, (terminal.point.y for terminal in terminals)),
        )
        if found is not None and (best is None or found.cost < best.cost):
            best = found
        # A way through a full channel is the window's last resort, not the diagram's: look further.
        if best is not None and not _through_a_full_channel(best.points, passage):
            return best
    return best


def _through_a_full_channel(points: Sequence[Point], passage: Passage) -> bool:
    return any(passage.crowding(a, b) >= FULL for a, b in zip(points, points[1:], strict=False))
