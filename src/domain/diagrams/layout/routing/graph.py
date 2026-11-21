"""The orthogonal visibility graph itself (GD 2009 §3): segments of visibility, stopped by obstacles.

Through every interesting point a level and an upright **segment** of visibility run, each as far as
the first obstacle on either side lets it — not across the whole diagram. A **node** is where a level
segment crosses an upright one, and each node is joined to the next node along either segment. That is
the paper's graph, and what makes it sparse: a line through one element's corner stops at the next
element, so it meets only the lines near it, where a grid of every line would cross them all.

What stops a segment is what blocks every connector alike: an element grown by `BUFFER`, and a text
region. A box border does not stop one; whether a connector may cross a border is its own question,
asked step by step (`Passage`).

The graph is built once for a scene. A search **joins** its terminals to it: their segments, the
nodes where those cross the scene's, and the joins those nodes split — kept aside, so the scene's graph
is shared by every search.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence

from src.domain.diagrams.layout.geometry import Extent, Point

#: Where a segment nothing stops ends.
_OPEN = math.inf

#: The four directions a route travels in: east, west, south, north.
EAST, WEST, SOUTH, NORTH = 0, 1, 2, 3


def _spanning(obstacles: Iterable[Extent], at: float, *, level: bool) -> list[tuple[float, float]]:
    """The stretch each obstacle takes of the line at *at*: those it lies strictly across."""
    if level:
        return [(rect.left, rect.right) for rect in obstacles if rect.top < at < rect.bottom]
    return [(rect.top, rect.bottom) for rect in obstacles if rect.left < at < rect.right]


def _free(stretches: Iterable[tuple[float, float]], along: float) -> tuple[float, float] | None:
    """The free stretch of a line about *along*, between the obstacles on it; None inside one."""
    low, high = -_OPEN, _OPEN
    for start, end in stretches:
        if start < along < end:
            return None
        if end <= along:
            low = max(low, end)
        elif start >= along:
            high = min(high, start)
    return low, high


def _segments(
    points: Iterable[tuple[float, float]], obstacles: Sequence[Extent], *, level: bool,
) -> list[tuple[float, float, float]]:
    """The segments of visibility through *points*, as (line, low, high), in order."""
    along_line: dict[float, set[float]] = defaultdict(set)
    for x, y in points:
        along_line[y if level else x].add(x if level else y)
    found: set[tuple[float, float, float]] = set()
    for at, alongs in along_line.items():
        stretches = _spanning(obstacles, at, level=level)
        for along in alongs:
            if (free := _free(stretches, along)) is not None:
                found.add((at, *free))
    return sorted(found)


class _Segments:
    """Segments in one orientation, found by their line and a position along it."""

    def __init__(self, segments: list[tuple[float, float, float]]) -> None:
        self.segments = segments
        self.on_line: dict[float, list[int]] = defaultdict(list)
        self.lows: dict[float, list[float]] = defaultdict(list)
        for index, (at, low, _high) in enumerate(segments):
            self.on_line[at].append(index)
            self.lows[at].append(low)
        self.lines = sorted(self.on_line)

    def holding(self, at: float, along: float) -> int:
        """The segment on the line *at* that holds *along*, or -1."""
        lows = self.lows.get(at)
        if lows is None:
            return -1
        position = bisect_right(lows, along) - 1
        if position < 0:
            return -1
        index = self.on_line[at][position]
        return index if along <= self.segments[index][2] else -1

    def crossing(self, at: float, low: float, high: float) -> Iterable[tuple[float, int]]:
        """Each segment of the other orientation's lines from *low* to *high* that holds *at*."""
        for line in self.lines[bisect_left(self.lines, low) : bisect_right(self.lines, high)]:
            if (index := self.holding(line, at)) >= 0:
                yield line, index


class Graph:
    """The scene's orthogonal visibility graph: nodes, and each node's next node in each direction."""

    def __init__(self, obstacles: Sequence[Extent], points: Iterable[Point]) -> None:
        self.obstacles = list(obstacles)
        corners = {(point.x, point.y) for point in points}
        self.level = _Segments(_segments(corners, self.obstacles, level=True))
        self.upright = _Segments(_segments(corners, self.obstacles, level=False))
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.at: dict[tuple[float, float], int] = {}
        self.level_nodes: list[list[int]] = [[] for _ in self.level.segments]
        self.upright_nodes: list[list[int]] = [[] for _ in self.upright.segments]
        for index, (y, low, high) in enumerate(self.level.segments):
            for x, upright in self.upright.crossing(y, low, high):
                node = len(self.xs)
                self.xs.append(x)
                self.ys.append(y)
                self.at[(x, y)] = node
                self.level_nodes[index].append(node)
                self.upright_nodes[upright].append(node)
        self.level_along = [[self.xs[node] for node in nodes] for nodes in self.level_nodes]
        self.upright_along = [[self.ys[node] for node in nodes] for nodes in self.upright_nodes]
        self.next = [-1] * (4 * len(self.xs))
        for nodes in self.level_nodes:
            for one, other in zip(nodes, nodes[1:], strict=False):
                self.next[4 * one + EAST], self.next[4 * other + WEST] = other, one
        for nodes in self.upright_nodes:
            for one, other in zip(nodes, nodes[1:], strict=False):
                self.next[4 * one + SOUTH], self.next[4 * other + NORTH] = other, one

    def joined(self, points: Iterable[Point]) -> Joined:
        """This graph with *points* joined to it, for one search."""
        return Joined(self, points)


class Joined:
    """A scene's graph with one search's terminals joined to it, the scene's graph left as it was."""

    def __init__(self, graph: Graph, points: Iterable[Point]) -> None:
        self._graph = graph
        self._base = len(graph.xs)
        self._xs: list[float] = []
        self._ys: list[float] = []
        self._at: dict[tuple[float, float], int] = {}
        self._next: dict[int, int] = {}
        own = sorted({(point.x, point.y) for point in points})
        # A terminal's segment is the scene's where one holds it already; else a segment of its own,
        # numbered after the scene's.
        level = self._segments_through(own, graph.level, level=True)
        upright = self._segments_through(own, graph.upright, level=False)
        new_level = [(index, segment) for index, segment in level if index >= len(graph.level.segments)]
        new_upright = [(index, segment) for index, segment in upright if index >= len(graph.upright.segments)]
        on_level: dict[int, set[tuple[float, float]]] = defaultdict(set)
        on_upright: dict[int, set[tuple[float, float]]] = defaultdict(set)
        for index, (y, low, high) in new_level:
            for x, other in graph.upright.crossing(y, low, high):
                on_level[index].add((x, y))
                on_upright[other].add((x, y))
            for other, (x, other_low, other_high) in new_upright:
                if low <= x <= high and other_low <= y <= other_high:
                    on_level[index].add((x, y))
                    on_upright[other].add((x, y))
        for index, (x, low, high) in new_upright:
            for y, other in graph.level.crossing(x, low, high):
                on_upright[index].add((x, y))
                on_level[other].add((x, y))
        # Where a terminal's segment crosses another there is a node no scene segment had.
        for (x, y) in sorted({point for points_on in on_level.values() for point in points_on} - graph.at.keys()):
            self._at[(x, y)] = self._base + len(self._xs)
            self._xs.append(x)
            self._ys.append(y)
        for index, points_on in sorted(on_level.items()):
            scene = index < len(graph.level_nodes)
            nodes, along = (graph.level_nodes[index], graph.level_along[index]) if scene else ([], [])
            self._link(nodes, along, points_on, EAST, WEST, by_x=True)
        for index, points_on in sorted(on_upright.items()):
            scene = index < len(graph.upright_nodes)
            nodes, along = (graph.upright_nodes[index], graph.upright_along[index]) if scene else ([], [])
            self._link(nodes, along, points_on, SOUTH, NORTH, by_x=False)

    def _segments_through(
        self, own: Sequence[tuple[float, float]], segments: _Segments, *, level: bool,
    ) -> list[tuple[int, tuple[float, float, float]]]:
        found: dict[tuple[float, float, float], int] = {}
        added = len(segments.segments)
        for x, y in own:
            at, along = (y, x) if level else (x, y)
            free = _free(_spanning(self._graph.obstacles, at, level=level), along)
            if free is None or (segment := (at, *free)) in found:
                continue
            index = segments.holding(at, along)
            if index < 0:
                index, added = added, added + 1
            found[segment] = index
        return sorted(((index, segment) for segment, index in found.items()), key=lambda pair: pair[0])

    def _link(
        self, scene_nodes: Sequence[int], scene_along: Sequence[float], points_on: Iterable[tuple[float, float]],
        forward: int, back: int, *, by_x: bool,
    ) -> None:
        """Joins, along one segment, each node the search added to its neighbours there: the scene's
        nodes either side of it, or another added node where no scene node lies between."""
        added = sorted(
            (x if by_x else y, node) for x, y in points_on if (node := self.node_at(Point(x, y))) >= self._base
        )
        places = [bisect_left(scene_along, along) for along, _node in added]
        for index, (_along, node) in enumerate(added):
            place = places[index]
            if index > 0 and places[index - 1] == place:
                before = added[index - 1][1]
            else:
                before = scene_nodes[place - 1] if place > 0 else -1
            if index + 1 < len(added) and places[index + 1] == place:
                after = added[index + 1][1]
            else:
                after = scene_nodes[place] if place < len(scene_nodes) else -1
            if before >= 0:
                self._next[4 * node + back], self._next[4 * before + forward] = before, node
            if after >= 0:
                self._next[4 * node + forward], self._next[4 * after + back] = after, node

    def node_at(self, point: Point) -> int:
        key = (point.x, point.y)
        node = self._graph.at.get(key)
        return node if node is not None else self._at[key]

    def x(self, node: int) -> float:
        return self._graph.xs[node] if node < self._base else self._xs[node - self._base]

    def y(self, node: int) -> float:
        return self._graph.ys[node] if node < self._base else self._ys[node - self._base]

    def next(self, node: int, direction: int) -> int:
        """The next node from *node* in *direction*, or -1."""
        key = 4 * node + direction
        joined = self._next.get(key)
        if joined is not None:
            return joined
        return self._graph.next[key] if node < self._base else -1

    @property
    def size(self) -> int:
        """Every node, the scene's and the search's."""
        return self._base + len(self._xs)
