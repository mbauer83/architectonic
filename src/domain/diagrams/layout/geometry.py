"""Points, extents and courses in a picture's own coordinates: x to the right, y downwards.

Extents throughout, not outlines: a shape with cut or rounded corners is reasoned about by the
rectangle it occupies. That is exact for everything asked here except a line grazing a cut corner,
which is why every question takes a *margin* — how far inside counts as inside.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def distance_to(self, other: Point) -> float:
        return math.hypot(other.x - self.x, other.y - self.y)


@dataclass(frozen=True)
class Extent:
    """The rectangle a shape occupies."""

    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def around(cls, points: Iterable[Point]) -> Extent | None:
        """The smallest extent holding every point, or None for no points."""
        held = tuple(points)
        if not held:
            return None
        return cls(
            left=min(p.x for p in held),
            top=min(p.y for p in held),
            right=max(p.x for p in held),
            bottom=max(p.y for p in held),
        )

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def centre(self) -> Point:
        return Point((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    def shrunk_by(self, margin: float) -> Extent | None:
        """This extent with *margin* taken off every side, or None where nothing is left."""
        inner = Extent(self.left + margin, self.top + margin, self.right - margin, self.bottom - margin)
        return inner if inner.width > 0 and inner.height > 0 else None

    def holds(self, point: Point) -> bool:
        return self.left <= point.x <= self.right and self.top <= point.y <= self.bottom

    def encloses(self, other: Extent, *, slack: float = 0.0) -> bool:
        """Whether *other* lies wholly inside, allowing it to poke out by *slack*."""
        return (
            self.left - slack <= other.left
            and self.top - slack <= other.top
            and other.right <= self.right + slack
            and other.bottom <= self.bottom + slack
        )

    def overlap_with(self, other: Extent) -> Extent | None:
        """The rectangle both occupy, or None where they are apart or only touch."""
        shared = Extent(
            max(self.left, other.left),
            max(self.top, other.top),
            min(self.right, other.right),
            min(self.bottom, other.bottom),
        )
        return shared if shared.width > 0 and shared.height > 0 else None

    def distance_to(self, point: Point) -> float:
        """How far *point* is from this extent; zero inside it."""
        return math.hypot(
            max(self.left - point.x, 0.0, point.x - self.right),
            max(self.top - point.y, 0.0, point.y - self.bottom),
        )

    def is_entered_by(self, start: Point, end: Point) -> bool:
        """Whether the straight segment from *start* to *end* has any point inside this extent.

        Liang–Barsky clipping: the segment is cut down against each side in turn, and it enters
        the extent exactly when something of it survives all four.
        """
        dx, dy = end.x - start.x, end.y - start.y
        entering, leaving = 0.0, 1.0
        for direction, distance in (
            (-dx, start.x - self.left),
            (dx, self.right - start.x),
            (-dy, start.y - self.top),
            (dy, self.bottom - start.y),
        ):
            if direction == 0:
                if distance < 0:
                    return False
                continue
            reach = distance / direction
            if direction < 0:
                entering = max(entering, reach)
            else:
                leaving = min(leaving, reach)
            if entering > leaving:
                return False
        return True


def course_length(course: Sequence[Point]) -> float:
    """How long a course is, walked point to point."""
    return sum(course[i].distance_to(course[i + 1]) for i in range(len(course) - 1))


def _turn(a: Point, b: Point, c: Point) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Whether segment a–b and segment c–d pass through each other.

    A proper crossing only: each segment's ends lie strictly on opposite sides of the other. Two
    segments that touch at an end, or run along each other, do not cross.
    """
    return _turn(a, b, c) * _turn(a, b, d) < 0 and _turn(c, d, a) * _turn(c, d, b) < 0


def courses_cross(first: Sequence[Point], second: Sequence[Point]) -> int:
    """How many times two courses pass through each other."""
    return sum(
        1
        for i in range(len(first) - 1)
        for j in range(len(second) - 1)
        if segments_cross(first[i], first[i + 1], second[j], second[j + 1])
    )
