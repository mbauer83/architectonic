"""The orthogonal visibility graph's interesting points, and what blocks a step along it.

The paper's interesting points are the corners of every obstacle and every connector's points; its
graph (`graph`) is the segments of visibility through them. Here the points are the corners of each
element moved out by `BUFFER`, of each text region moved out by the same, of each box border moved
`BORDER_OFFSET` to either side, and the connector's own stub ends. All of them whole numbers, rounded
outward, so every bend a route takes is one and the two languages place it on the same pixel.

What blocks, for one connector (`Passage`):

* an element, grown by `BUFFER` — whichever element it is, its own ends included once the route has
  left them by its stubs;
* a text region, as given (it is padded already);
* a **wall**: a box that holds neither of the connector's ends, or a box that is one of its ends.
  A box that holds an end is crossed, at right angles, which is how a route reaches a member;
* a run **along** any box's border closer than `LINE_CLEARANCE` — crossing is fine, following never;
* the connector's **bounds** (`Bounds`): it stays inside the smallest box holding both its ends, it
  never leaves a box holding its target once inside, and never enters again a box holding its source
  once outside. So a box's border is crossed once, the way the route is going. Where no route keeps
  its bounds, the router searches again without them.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.routing.graph import Graph
from src.domain.diagrams.layout.routing.lines import Lines, Stubs
from src.domain.diagrams.layout.routing.scene import BORDER_OFFSET, BUFFER, IDEAL_SEPARATION, RoutingScene

#: The side of one cell of the index that answers which rectangles are near a place.
_CELL = 128.0

#: How much two spans must share to count as running along each other.
_SHARED = 1.0

#: How far either side of a run its room is looked for.
_ROOM_LOOKED_FOR = 60.0

#: What a run in a channel already full counts as, in routes alongside: a long way round is cheaper.
FULL = 100


def grown_outward(extent: Extent, by: float) -> Extent:
    """*extent* grown by *by* on every side, its edges rounded outward to whole numbers."""
    return Extent(
        math.floor(extent.left - by), math.floor(extent.top - by),
        math.ceil(extent.right + by), math.ceil(extent.bottom + by),
    )


def _enters(rect: Extent, a: Point, b: Point) -> bool:
    """Whether the axis-aligned segment a–b has any point strictly inside *rect*."""
    if a.y == b.y:
        return rect.top < a.y < rect.bottom and max(rect.left, min(a.x, b.x)) < min(rect.right, max(a.x, b.x))
    return rect.left < a.x < rect.right and max(rect.top, min(a.y, b.y)) < min(rect.bottom, max(a.y, b.y))


class _Index:
    """Rectangles by the cells they cover."""

    def __init__(self, rects: Iterable[Extent]) -> None:
        self._cells: dict[tuple[int, int], list[Extent]] = defaultdict(list)
        for rect in rects:
            for column in range(math.floor(rect.left / _CELL), math.floor(rect.right / _CELL) + 1):
                for row in range(math.floor(rect.top / _CELL), math.floor(rect.bottom / _CELL) + 1):
                    self._cells[(column, row)].append(rect)

    def near(self, left: float, top: float, right: float, bottom: float) -> list[Extent]:
        first_column, last_column = math.floor(left / _CELL), math.floor(right / _CELL)
        first_row, last_row = math.floor(top / _CELL), math.floor(bottom / _CELL)
        if first_column == last_column and first_row == last_row:
            return self._cells.get((first_column, first_row), [])
        found: dict[int, Extent] = {}
        for column in range(first_column, last_column + 1):
            for row in range(first_row, last_row + 1):
                for rect in self._cells.get((column, row), ()):
                    found[id(rect)] = rect
        return list(found.values())


def _borders(boxes: Iterable[Extent]) -> Lines:
    lines = Lines()
    for box in boxes:
        corners = (Point(box.left, box.top), Point(box.right, box.top), Point(box.right, box.bottom),
                   Point(box.left, box.bottom))
        for index, corner in enumerate(corners):
            lines.add(corner, corners[(index + 1) % 4])
    return lines


def _corners(rect: Extent) -> tuple[Point, ...]:
    return (Point(rect.left, rect.top), Point(rect.right, rect.top), Point(rect.left, rect.bottom),
            Point(rect.right, rect.bottom))


def _interesting(scene: RoutingScene, grown: Iterable[Extent]) -> list[Point]:
    """The graph's interesting points: the corners of every element and text region moved out by
    `BUFFER`, and of every box border moved `BORDER_OFFSET` to either side."""
    points = [corner for rect in grown for corner in _corners(rect)]
    points += [corner for text in scene.text.values() for corner in _corners(grown_outward(text, BUFFER))]
    for box in scene.boxes.values():
        xs = (math.floor(box.left - BORDER_OFFSET), math.ceil(box.left + BORDER_OFFSET),
              math.floor(box.right - BORDER_OFFSET), math.ceil(box.right + BORDER_OFFSET))
        ys = (math.floor(box.top - BORDER_OFFSET), math.ceil(box.top + BORDER_OFFSET),
              math.floor(box.bottom - BORDER_OFFSET), math.ceil(box.bottom + BORDER_OFFSET))
        points += [Point(x, y) for x in xs for y in ys]
    return points


class Visibility:
    """Everything about a scene a connector's search asks, built once for the scene."""

    def __init__(self, scene: RoutingScene) -> None:
        self.scene = scene
        self.grown = {key: grown_outward(extent, BUFFER) for key, extent in scene.elements.items()}
        self.blocking = _Index([*self.grown.values(), *scene.text.values()])
        self.borders = _borders(scene.boxes.values())
        self.graph = Graph([*self.grown.values(), *scene.text.values()], _interesting(scene, self.grown.values()))

    def passage(self, ends: tuple[str, str], *, bounded: bool = True) -> Passage:
        """What blocks the connector from *ends[0]* to *ends[1]*; with *bounded*, its bounds too."""
        own = [self.scene.extent_of(end) for end in ends]
        walls = [
            box for key, box in self.scene.boxes.items()
            if key in ends or not any(box.encloses(end) and box != end for end in own)
        ]
        return Passage(self, walls, bounds=self.bounds(ends) if bounded else Bounds())

    def bounds(self, ends: tuple[str, str]) -> Bounds:
        """The boxes the connector from *ends[0]* to *ends[1]* keeps to, and crosses once."""
        source, target = (self.scene.extent_of(end) for end in ends)
        holding = [
            (key, box) for key, box in self.scene.boxes.items()
            if key not in ends and box not in (source, target)
        ]
        both = [
            (box.width * box.height, key, box) for key, box in holding if box.encloses(source) and box.encloses(target)
        ]
        return Bounds(
            within=min(both)[2] if both else None,
            stays_in=tuple(box for _key, box in holding if box.encloses(target) and not box.encloses(source)),
            stays_out=tuple(box for _key, box in holding if box.encloses(source) and not box.encloses(target)),
        )


@dataclass(frozen=True)
class Bounds:
    """Where one connector's route may go, as boxes: one it stays inside, ones it crosses only one way."""

    #: The smallest box holding both ends: the route stays inside it.
    within: Extent | None = None
    #: Boxes holding the target and not the source: once inside one, the route does not leave it.
    stays_in: tuple[Extent, ...] = ()
    #: Boxes holding the source and not the target: once outside one, the route does not come back.
    stays_out: tuple[Extent, ...] = ()

    def broken_by(self, a: Point, b: Point) -> bool:
        """Whether the step from *a* to *b* leaves the route's bounds."""
        if self.within is not None and not (self.within.holds(a) and self.within.holds(b)):
            return True
        return any(box.holds(a) and not box.holds(b) for box in self.stays_in) or any(
            not box.holds(a) and box.holds(b) for box in self.stays_out
        )


class Passage:
    """What blocks one connector: the scene's obstacles, and its own walls."""

    def __init__(
        self, visibility: Visibility, walls: Sequence[Extent], also: Sequence[Extent] = (), crowd: Lines | None = None,
        bounds: Bounds | None = None, stubs: tuple[Stubs, str] | None = None,
    ) -> None:
        self._visibility = visibility
        self.walls = walls
        self._also = also
        self._walls = _Index([*walls, *also])
        self._crowd = crowd
        self.bounds = bounds or Bounds()
        self._stubs = stubs

    def adding(
        self, rects: Sequence[Extent], crowd: Lines | None = None, stubs: tuple[Stubs, str] | None = None,
    ) -> Passage:
        """This passage with *rects* blocking as well, *crowd* the routes found before it, and *stubs*
        the stubs no run goes along but those of the connector named with them."""
        return Passage(
            self._visibility, self.walls, [*self._also, *rects], crowd or self._crowd, self.bounds,
            stubs or self._stubs,
        )

    def unbounded(self) -> Passage:
        """This passage without its bounds: for a connector no route within them reaches."""
        return Passage(self._visibility, self.walls, self._also, self._crowd, None, self._stubs)

    def crowding(self, a: Point, b: Point) -> int:
        """How crowded the run a–b is: the routes found before that run alongside it within the ideal
        separation — and `FULL` besides where the channel it lies in, between what blocks on either
        side, already holds as many lines as fit there, so a search goes round rather than queue for
        room nudging cannot make."""
        if self._crowd is None or self._crowd.near(a, b, _ROOM_LOOKED_FOR) == 0:
            return 0
        least, most = self._room_across(a, b)
        in_channel = self._crowd.between(a, b, least, most)
        fits = math.floor((most - least) / IDEAL_SEPARATION) + 1 - self._visibility.borders.between(a, b, least, most)
        return self._crowd.near(a, b, IDEAL_SEPARATION) + (FULL if in_channel + 1 > fits else 0)

    def _room_across(self, a: Point, b: Point) -> tuple[float, float]:
        """The channel the run a–b lies in: from what blocks on one side to what blocks on the other."""
        level = a.y == b.y
        at = a.y if level else a.x
        low, high = (min(a.x, b.x), max(a.x, b.x)) if level else (min(a.y, b.y), max(a.y, b.y))
        reach = _ROOM_LOOKED_FOR
        box = (low, at - reach, high, at + reach) if level else (at - reach, low, at + reach, high)
        least, most = at - reach, at + reach
        for rect in self._near(*box):
            r_low, r_high = (rect.left, rect.right) if level else (rect.top, rect.bottom)
            r_near, r_far = (rect.top, rect.bottom) if level else (rect.left, rect.right)
            if max(r_low, low) < min(r_high, high):
                if r_far <= at:
                    least = max(least, r_far)
                elif r_near >= at:
                    most = min(most, r_near)
        return least, most

    def _near(self, left: float, top: float, right: float, bottom: float) -> list[Extent]:
        return [
            *self._visibility.blocking.near(left, top, right, bottom),
            *self._walls.near(left, top, right, bottom),
        ]

    def point_blocked(self, point: Point) -> bool:
        return any(
            rect.left < point.x < rect.right and rect.top < point.y < rect.bottom
            for rect in self._near(point.x, point.y, point.x, point.y)
        )

    def step_blocked(self, a: Point, b: Point, *, ignoring: Sequence[Extent] = ()) -> bool:
        """Whether the axis-aligned step a–b enters an obstacle or a wall, or runs along a border."""
        near = self._near(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))
        return (
            any(_enters(rect, a, b) for rect in near if rect not in ignoring)
            or self._visibility.borders.along(a, b)
            or self.bounds.broken_by(a, b)
            or (self._stubs is not None and self._stubs[0].along(a, b, self._stubs[1]))
        )

