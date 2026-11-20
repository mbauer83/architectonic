"""The decorations at a relation's ends — arrowhead, diamond, dot — drawn where a relation ends now.

The one place a relation's end decoration is placed. A decoration is drawn in an **end frame**: the
point on the element's border the relation arrives at, and the heading it arrives with. Whoever has
decorations drawn in one frame hands them over with that frame and the frame they are wanted in, and
gets them back turned and carried there. Today the decorations are the ones PlantUML drew, taken with
the frame they were drawn in (`frame_as_drawn`); a notation corrected from the relationship-notation
declaration is the same call with decorations drawn in a frame of its own choosing.

A relation's line stops short of some decorations — it ends at the base of a hollow head, not at its
tip — so the frame also says how far short the line was drawn, and `stopping_short` gives a course
the same gap at its new ends.

The decoration's tip is placed exactly at the route's end, which a port puts on the element's border:
so a decoration cannot be drawn away from its element, whatever the line did where PlantUML drew it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from xml.etree.ElementTree import Element

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import EndMark, MarkShape
from src.infrastructure.rendering.layout.svg_markup import Motion, moved

#: How far back along a line its heading is taken from. A drawn line may hook at its very end —
#: PlantUML overshoots a box's border and comes back — so the last step alone can face the wrong way.
_HEADING_TAKEN_OVER = 8.0

#: The longest gap a line is taken to leave before its end, for the longest decoration drawn there.
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


def _unit(dx: float, dy: float) -> tuple[float, float] | None:
    length = math.hypot(dx, dy)
    return (dx / length, dy / length) if length > 0 else None


def frame_as_drawn(marks: Sequence[EndMark], course: Sequence[Point], end: Extent) -> EndFrame:
    """The frame the decorations at one end were drawn in, read off the decorations themselves.

    *course* runs towards the element occupying *end*. The frame is where the decorations touch the
    element — their point nearest it — and the way they point, from their middle to that point. It is
    not read off the line: PlantUML's line hooks in its last few pixels, and a heading taken from
    the hook placed an arrowhead beside its element instead of against it. A dot points nowhere, so
    the line gives its heading; an end with no decoration is where the line ends.
    """
    line_end, line_heading = course[-1], heading_at_end(course)
    shaped = [point for mark in marks if mark.shape is not MarkShape.ELLIPSE for point in mark.outline]
    dots = [Extent.around(mark.outline) for mark in marks if mark.shape is MarkShape.ELLIPSE]
    if shaped:
        tip = min(shaped, key=end.distance_to)
        middle = Point(sum(point.x for point in shaped) / len(shaped), sum(point.y for point in shaped) / len(shaped))
        heading = _unit(tip.x - middle.x, tip.y - middle.y) or line_heading
    elif dots and (dot := dots[0]) is not None:
        heading, radius = line_heading, dot.width / 2
        tip = Point(dot.centre.x + heading[0] * radius, dot.centre.y + heading[1] * radius)
    else:
        return EndFrame(line_end, line_heading, 0.0)
    gap = (tip.x - line_end.x) * heading[0] + (tip.y - line_end.y) * heading[1]
    return EndFrame(tip, heading, max(0.0, min(gap, _LONGEST_GAP)))


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
