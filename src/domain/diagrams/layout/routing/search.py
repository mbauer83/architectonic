"""A* over the visibility graph, from any of a connector's starts to any of its goals (GD 2009 §4).

A state is a node of the graph and the direction the route travels into it; a step costs its length
and `BEND_PENALTY` where it turns. The estimate is the Manhattan distance to the nearest goal, weighted
by `EAGERNESS`: the route found costs at most that much more than the cheapest, and the search
explores a fraction of the states. Ties are broken by the order states were reached, so both languages
find the same one.

A start is a stub end, travelling outward from its port; a goal is a stub end, entered travelling
towards its port. Reaching a goal in another direction costs the bend into the stub. The search first
looks within a window round its terminals — wider the further apart they are — and widens it only when
the window holds no way, or only one through a channel already full.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.routing.graph import Graph, Joined
from src.domain.diagrams.layout.routing.scene import BEND_PENALTY, CHANNEL_FULL, CROWDING
from src.domain.diagrams.layout.routing.visibility import FULL, Passage

#: The four directions a route travels in, as steps: east, west, south, north.
DIRECTIONS: tuple[tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))

#: The direction opposite each direction.
REVERSE: tuple[int, ...] = (1, 0, 3, 2)

#: How much the distance still to go is over-weighted. Above 1 the search commits to a promising way
#: rather than proving it the very cheapest; what it finds costs at most this much more.
EAGERNESS = 1.5

#: How far round its terminals a search looks first; then three times as far; then everywhere.
WINDOW = 200.0

#: How far beyond its terminals a far-reaching search first looks, as a share of how far apart they are:
#: a line across a wide picture that must leave its terminals' band to go round something finds that way
#: in its first window, rather than exhausting a window a band high before widening.
SPAN_SHARE = 0.1


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


def step_cost(length: float, crowding: int) -> float:
    """What a step costs: its length, a share more for each route already alongside, and a fixed sum
    where its channel is full. Bounded so: a crowded way costs a fraction of its length more and a
    full one two bends more, so neither buys a detour longer than that."""
    full = crowding >= FULL
    alongside = crowding - FULL if full else crowding
    return length * (1 + CROWDING * alongside) + (CHANNEL_FULL if full else 0.0)


def _windows(terminals: Sequence[Terminal]) -> list[Extent | None]:
    left = min(terminal.point.x for terminal in terminals)
    top = min(terminal.point.y for terminal in terminals)
    right = max(terminal.point.x for terminal in terminals)
    bottom = max(terminal.point.y for terminal in terminals)
    first = max(WINDOW, SPAN_SHARE * max(right - left, bottom - top))
    return [
        Extent(left - reach, top - reach, right + reach, bottom + reach) for reach in (first, 3 * first)
    ] + [None]


def without_straight_points(points: Sequence[Point]) -> tuple[Point, ...]:
    kept = [points[0]]
    for index in range(1, len(points) - 1):
        before, here, after = kept[-1], points[index], points[index + 1]
        if not ((before.x == here.x == after.x) or (before.y == here.y == after.y)):
            kept.append(here)
    return (*kept, points[-1]) if len(points) > 1 else tuple(kept)


def _search_within(
    starts: Sequence[Terminal], goals: Sequence[Terminal], passage: Passage, graph: Joined, window: Extent | None,
) -> Found | None:
    goals_at: dict[int, list[int]] = {}
    for index, goal in enumerate(goals):
        goals_at.setdefault(graph.node_at(goal.point), []).append(index)
    goal_points = [(goal.point.x, goal.point.y) for goal in goals]

    def estimate(x: float, y: float) -> float:
        least = math.inf
        for goal_x, goal_y in goal_points:
            least = min(least, abs(goal_x - x) + abs(goal_y - y))
        return least

    steps: dict[int, tuple[int, float] | None] = {}

    def step(node: int, turn: int) -> tuple[int, float] | None:
        """Where the step from *node* in direction *turn* leads and what it costs, or None where it is
        blocked or leaves the window: asked once per step, however many states reach its node."""
        key = 4 * node + turn
        if key not in steps:
            steps[key] = None
            reached = graph.next(node, turn)
            if reached >= 0:
                x, y = graph.x(reached), graph.y(reached)
                inside = window is None or (window.left <= x <= window.right and window.top <= y <= window.bottom)
                here, there = Point(graph.x(node), graph.y(node)), Point(x, y)
                if inside and not passage.step_blocked(here, there):
                    length = abs(x - here.x) + abs(y - here.y)
                    steps[key] = (reached, step_cost(length, passage.crowding(here, there)))
        return steps[key]

    best: dict[int, float] = {}
    came: dict[int, int] = {}
    began: dict[int, int] = {}
    # f, order, node, direction, goal index (-1: an ordinary state; else: finishing at that goal)
    frontier: list[tuple[float, int, int, int, int]] = []
    order = 0
    for start in starts:
        node = graph.node_at(start.point)
        state = 4 * node + start.direction
        if state not in best:
            best[state], came[state], began[state] = 0.0, -1, start.tag
            f_start = EAGERNESS * estimate(start.point.x, start.point.y)
            heapq.heappush(frontier, (f_start, order, node, start.direction, -1))
            order += 1
    while frontier:
        f, _order, node, last, finishing = heapq.heappop(frontier)
        state = 4 * node + last
        if finishing >= 0:
            return Found(_walked_back(state, came, graph), began[state], goals[finishing].tag, f)
        g = best[state]
        if f > g + EAGERNESS * estimate(graph.x(node), graph.y(node)):
            continue  # reached again more cheaply since this entry was made
        for index in goals_at.get(node, ()):
            if last == REVERSE[goals[index].direction]:
                continue  # turning back into the stub would run along it
            finish = g + (BEND_PENALTY if last != goals[index].direction else 0.0)
            heapq.heappush(frontier, (finish, order, node, last, index))
            order += 1
        for turn in range(4):
            if turn == REVERSE[last] or (taken := step(node, turn)) is None:
                continue
            reached, length = taken
            then = 4 * reached + turn
            cost = g + length + (BEND_PENALTY if turn != last else 0.0)
            if cost < best.get(then, math.inf):
                best[then], came[then], began[then] = cost, state, began[state]
                f_then = cost + EAGERNESS * estimate(graph.x(reached), graph.y(reached))
                heapq.heappush(frontier, (f_then, order, reached, turn, -1))
                order += 1
    return None


def _walked_back(state: int, came: dict[int, int], graph: Joined) -> tuple[Point, ...]:
    points: list[Point] = []
    while state >= 0:
        points.append(Point(graph.x(state // 4), graph.y(state // 4)))
        state = came[state]
    return without_straight_points(points[::-1])


def search(starts: Sequence[Terminal], goals: Sequence[Terminal], passage: Passage, graph: Graph) -> Found | None:
    """The cheapest route from any start to any goal over *graph*, or None."""
    terminals = [*starts, *goals]
    joined = graph.joined(terminal.point for terminal in terminals)
    best: Found | None = None
    for window in _windows(terminals):
        if window is None and best is not None:
            break  # the whole diagram is searched only where no window held any way at all
        found = _search_within(starts, goals, passage, joined, window)
        if found is not None and (best is None or found.cost < best.cost):
            best = found
        # A way through a full channel is the window's last resort, not the diagram's: look further.
        if best is not None and not _through_a_full_channel(best.points, passage):
            return best
    return best


def _through_a_full_channel(points: Sequence[Point], passage: Passage) -> bool:
    return any(passage.crowding(a, b) >= FULL for a, b in zip(points, points[1:], strict=False))
