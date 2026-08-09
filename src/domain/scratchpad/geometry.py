"""Canvas geometry, and the grid every coordinate is written on.

Separate from the aggregate because it is the one part with no scratchpad vocabulary in it: a point
is a point. It exists mainly for `snap`, which is what keeps a git-backed canvas reviewable — the
pointer reports sub-pixel positions, so without snapping, resting a hand on a note produces a diff.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Pixels. Coarse enough that no hand movement below a deliberate nudge survives into a commit,
#: fine enough that a person arranging notes never feels the grid.
GRID = 5


def snap(value: float) -> int:
    return int(round(value / GRID) * GRID)


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def contains(self, point: Point) -> bool:
        """Whether *point* — a note's top-left corner — lies in this frame.

        The corner rather than the centre, because it is the corner the layout stores and the
        corner a drag positions; asking about the centre would make containment depend on a note's
        size, which the canvas is free to change when its title wraps.
        """
        return (
            self.x <= point.x < self.x + self.width
            and self.y <= point.y < self.y + self.height
        )


def snap_point(point: Point) -> Point:
    return Point(snap(point.x), snap(point.y))


def snap_rect(rect: Rect) -> Rect:
    return Rect(snap(rect.x), snap(rect.y), snap(rect.width), snap(rect.height))
