"""The decorations at a relation's ends — arrowhead, diamond, dot — drawn where a relation ends now.

The one place a relation's end decoration is placed. A decoration is drawn in an **end frame**: the
point on the element's border the relation arrives at, and the heading it arrives with. Whoever has
decorations drawn in one frame hands them over with that frame and the frame they are wanted in, and
gets them back turned and carried there. Today the decorations are the ones PlantUML drew, taken with
the frame it drew them in (`frame_as_drawn`); a notation corrected from the relationship-notation
declaration is the same call with decorations drawn in a frame of its own choosing.

A relation's line stops short of some decorations — it ends at the base of a hollow head, not at its
tip — so the frame also says how far short the line was drawn, and `stopping_short` gives a course
the same gap at its new ends.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from xml.etree.ElementTree import Element

from src.domain.diagrams.layout.geometry import Extent, Point
from src.infrastructure.rendering.layout.svg_markup import Motion, moved

#: How far back along a line its heading is taken from. A drawn line may hook at its very end —
#: PlantUML overshoots a box's border and comes back — so the last step alone can face the wrong way.
_HEADING_TAKEN_OVER = 8.0

#: The longest gap a line is taken to leave before its end. Further than this, the line simply ends
#: somewhere else than at the element, and the decoration is anchored where the line ends.
_LONGEST_GAP = 40.0

#: The shortest run a line keeps when it stops short of a decoration.
_SHORTEST_RUN = 1.0


@dataclass(frozen=True)
class EndFrame:
    """Where a relation's end is, which way the line arrives there, and how far short of it the line stops."""

    at: Point
    #: A unit vector along the line's last run, pointing at the element.
    heading: tuple[float, float]
    gap: float = 0.0


def heading_at_end(course: Sequence[Point]) -> tuple[float, float]:
    """Which way *course* is going when it ends, taken over its last few pixels."""
    end = course[-1]
    back = next(
        (point for point in reversed(course[:-1]) if point.distance_to(end) >= _HEADING_TAKEN_OVER), course[0]
    )
    length = back.distance_to(end)
    return ((end.x - back.x) / length, (end.y - back.y) / length) if length > 0 else (0.0, 1.0)


def _reach_to(extent: Extent, start: Point, heading: tuple[float, float]) -> float:
    """How far from *start* along *heading* the border of *extent* is; zero from inside it or past it."""
    entering, leaving = 0.0, math.inf
    for towards, low, high, position in (
        (heading[0], extent.left, extent.right, start.x), (heading[1], extent.top, extent.bottom, start.y),
    ):
        if towards == 0:
            if not low <= position <= high:
                return 0.0
            continue
        near, far = sorted(((low - position) / towards, (high - position) / towards))
        entering, leaving = max(entering, near), min(leaving, far)
    return entering if entering <= leaving else 0.0


def frame_as_drawn(course: Sequence[Point], end: Extent) -> EndFrame:
    """The frame a relation's end was drawn in: *course* runs towards the element occupying *end*."""
    heading, stops = heading_at_end(course), course[-1]
    gap = _reach_to(end, stops, heading)
    if gap > _LONGEST_GAP:
        gap = 0.0
    return EndFrame(Point(stops.x + heading[0] * gap, stops.y + heading[1] * gap), heading, gap)


def frame_at_end(course: Sequence[Point], gap: float) -> EndFrame:
    """The frame at the end of a course that runs all the way to its element's border."""
    return EndFrame(course[-1], heading_at_end(course), gap)


def placed_decorations(decorations: Sequence[Element], drawn: EndFrame, wanted: EndFrame) -> list[Element]:
    """Copies of *decorations*, drawn in the frame *drawn*, as they sit in the frame *wanted*."""
    motion = Motion.facing(drawn.at, drawn.heading, wanted.at, wanted.heading)
    return [moved(decoration, motion) for decoration in decorations]


def _pulled_back(end: Point, before: Point, gap: float) -> Point:
    run = before.distance_to(end)
    kept = max(0.0, min(gap, run - _SHORTEST_RUN))
    return Point(end.x + (before.x - end.x) / run * kept, end.y + (before.y - end.y) / run * kept) if run > 0 else end


def stopping_short(course: Sequence[Point], gap_at_start: float, gap_at_end: float) -> tuple[Point, ...]:
    """*course* with its two ends pulled back along their own runs by the gaps the line is drawn with."""
    return (
        _pulled_back(course[0], course[1], gap_at_start),
        *course[1:-1],
        _pulled_back(course[-1], course[-2], gap_at_end),
    )
