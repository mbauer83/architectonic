"""Where a rendered picture does not connect: an arrow reaching nothing, or a line over a shape.

**Why geometry and not the body.** Every other check this project makes about a diagram reads the
declarations or the PUML: complete by construction, and blind to what the layout engine then does with
them. A body can be valid, lay out without a warning, and still draw an arrow that stops in mid-air or
runs a return edge straight through the box it is returning to. That happened three times in one
release, and each time the body was read, the picture was *looked at*, and the defect survived both —
because a glance confirms the shapes and does not follow the arrowheads.

This reads the drawing itself and asks the one question a glance is bad at: does every arrow land on
something, and does every line stay off the shapes.

**What a defect is here.** Three kinds, and the third is the one that shipped:

* an arrowhead whose tip touches no shape and no line — it points into empty space;
* an arrowhead whose tip lands in the *interior* of a line running crosswise to it — the flow merges
  into another arrow instead of into a step, so the reader is left to guess where control went;
* a line segment crossing a shape's interior — the edge is drawn over content.

**What is not a defect.** A mid-edge direction marker: PlantUML puts an arrowhead partway along a long
return edge to say which way it runs. Its tip sits on a line *collinear* with the direction it points,
which is how it is told apart — it decorates its own path rather than arriving somewhere.

**The limit, stated because it cannot be closed from here.** A rendered SVG carries no edge identity:
segments are independent `<line>` elements with no notion of which edge they belong to. So an arrow
merging into a line that happens to run *parallel* to it is indistinguishable from a marker on its own
path, and is not reported. Arrows into empty space and lines over shapes are exact; crosswise merges
are exact; parallel merges are the blind spot. A picture this reports as clean can still hold one.

Straight-segment drawings only, which is what PlantUML's own layout emits. A picture drawn with curves
(`<path>`) offers this nothing, and `arrowheads_examined` says so rather than passing vacuously.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from defusedxml import ElementTree as SafeET

#: How far a tip may sit from a shape or a line and still count as touching it. PlantUML places an
#: arrowhead against the boundary it arrives at, so this absorbs rounding, not routing.
_TOUCHING = 3.0

#: How far along a segment a tip must be, from either end, before it counts as meeting the segment's
#: *interior* rather than its endpoint. An arrow arriving where two segments meet is a corner in one
#: path; an arrow arriving mid-span is a merge into a different one.
_INTERIOR_MARGIN = 6.0

#: Above this, a polygon is a shape being drawn; below it, and with few enough corners, it is an
#: arrowhead. The two populations are far apart — heads run about 35 square units, the smallest shape
#: PlantUML draws (a bare merge diamond) about 280 — so the threshold sits between them rather than on
#: either. Point count alone does not separate them: a merge diamond is four corners, like a head.
_SMALLEST_SHAPE_AREA = 200.0

#: Corners above which a polygon is a shape whatever its area. A decision hexagon has six.
_HEAD_CORNER_LIMIT = 4

#: How nearly parallel a segment must be to an arrow's direction to count as the arrow's own path.
#: cos 37° — generous, because the alternative to a false "marker" is a false defect report.
_COLLINEAR = 0.8

#: How far inside a shape a segment must run before it counts as crossing rather than touching it.
_OVER_A_SHAPE = 2.0


class Disconnection(StrEnum):
    """The ways a drawing fails to connect, in the words a reviewer would use."""

    REACHES_NOTHING = "an arrow reaching nothing"
    REACHES_ANOTHER_ARROW = "an arrow reaching another arrow"
    CROSSES_A_SHAPE = "a line crossing a shape"


@dataclass(frozen=True)
class DrawnDefect:
    """One place the picture does not connect, and enough of where to find it in the SVG."""

    disconnection: Disconnection
    at: tuple[float, float]
    detail: str


@dataclass(frozen=True)
class _Box:
    """A shape's extent. Bounding boxes throughout: a tip inside a rounded corner is still arriving."""

    left: float
    top: float
    right: float
    bottom: float

    def holds(self, point: tuple[float, float], *, slack: float) -> bool:
        x, y = point
        return (
            self.left - slack <= x <= self.right + slack
            and self.top - slack <= y <= self.bottom + slack
        )


@dataclass(frozen=True)
class _Segment:
    """One drawn line. Only the axis-aligned ones can be reasoned about this simply, and PlantUML's
    activity and sequence layouts draw nothing else."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def direction(self) -> tuple[float, float]:
        length = self.length or 1.0
        return ((self.x2 - self.x1) / length, (self.y2 - self.y1) / length)

    def nearest(self, point: tuple[float, float]) -> tuple[float, float]:
        """The point on this segment closest to *point*, and how far along the segment it lies."""
        length = self.length
        if length < 1.0:
            return (math.hypot(point[0] - self.x1, point[1] - self.y1), 0.0)
        along = max(
            0.0,
            min(
                1.0,
                ((point[0] - self.x1) * (self.x2 - self.x1) + (point[1] - self.y1) * (self.y2 - self.y1))
                / (length * length),
            ),
        )
        foot = (self.x1 + along * (self.x2 - self.x1), self.y1 + along * (self.y2 - self.y1))
        return (math.hypot(point[0] - foot[0], point[1] - foot[1]), along * length)

    def crosses(self, box: _Box) -> bool:
        """Does this segment run through *box*'s interior, rather than up to its edge?"""
        left, top = box.left + _OVER_A_SHAPE, box.top + _OVER_A_SHAPE
        right, bottom = box.right - _OVER_A_SHAPE, box.bottom - _OVER_A_SHAPE
        if right <= left or bottom <= top:
            return False
        if abs(self.x1 - self.x2) < 0.5:
            return left < self.x1 < right and max(min(self.y1, self.y2), top) < min(
                max(self.y1, self.y2), bottom
            )
        if abs(self.y1 - self.y2) < 0.5:
            return top < self.y1 < bottom and max(min(self.x1, self.x2), left) < min(
                max(self.x1, self.x2), right
            )
        return False


@dataclass(frozen=True)
class _Arrowhead:
    """A drawn arrowhead: where it points, and from where."""

    tip: tuple[float, float]
    direction: tuple[float, float]


@dataclass(frozen=True)
class DrawnPicture:
    """What a rendered picture connects, and where it does not.

    *arrowheads_examined* is part of the answer rather than a diagnostic aside: a picture drawn with
    curves yields none, and a caller that reads only `defects` would take that silence for health.
    """

    defects: tuple[DrawnDefect, ...]
    arrowheads_examined: int
    shapes_found: int


def _numbers(element: object, *names: str) -> tuple[float, ...] | None:
    """The named attributes as numbers, or None where any is absent or not one.

    Returned together rather than read one at a time so the absence of any one is a single answer:
    a shape missing a coordinate is not a shape, and partially-read geometry has no useful meaning.
    """
    get = getattr(element, "get", None)
    if get is None:
        return None
    values: list[float] = []
    for name in names:
        text = get(name)
        if text is None:
            return None
        try:
            values.append(float(text))
        except ValueError:
            return None
    return tuple(values)


def _corners(points: str) -> list[tuple[float, float]]:
    pairs = points.replace(",", " ").split()
    return [
        (float(pairs[i]), float(pairs[i + 1]))
        for i in range(0, len(pairs) - 1, 2)
    ]


def _polygon_area(corners: list[tuple[float, float]]) -> float:
    doubled = sum(
        corners[i][0] * corners[(i + 1) % len(corners)][1]
        - corners[(i + 1) % len(corners)][0] * corners[i][1]
        for i in range(len(corners))
    )
    return abs(doubled) / 2.0


def _head_of(corners: list[tuple[float, float]]) -> _Arrowhead:
    centre_x = sum(x for x, _ in corners) / len(corners)
    centre_y = sum(y for _, y in corners) / len(corners)
    tip = max(corners, key=lambda c: (c[0] - centre_x) ** 2 + (c[1] - centre_y) ** 2)
    span = math.hypot(tip[0] - centre_x, tip[1] - centre_y) or 1.0
    return _Arrowhead(tip=tip, direction=((tip[0] - centre_x) / span, (tip[1] - centre_y) / span))


def _read(svg: str) -> tuple[list[_Box], list[_Arrowhead], list[_Segment]]:
    root = SafeET.fromstring(svg.encode("utf-8"))
    boxes: list[_Box] = []
    heads: list[_Arrowhead] = []
    segments: list[_Segment] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "rect" and element.get("fill", "none") != "none":
            if (r := _numbers(element, "x", "y", "width", "height")) is not None:
                x, y, width, height = r
                boxes.append(_Box(x, y, x + width, y + height))
        elif tag == "ellipse":
            if (e := _numbers(element, "cx", "cy", "rx", "ry")) is not None:
                cx, cy, rx, ry = e
                boxes.append(_Box(cx - rx, cy - ry, cx + rx, cy + ry))
        elif tag == "polygon" and (corners := _corners(element.get("points", ""))):
            if len(corners) > _HEAD_CORNER_LIMIT or _polygon_area(corners) >= _SMALLEST_SHAPE_AREA:
                xs, ys = [c[0] for c in corners], [c[1] for c in corners]
                boxes.append(_Box(min(xs), min(ys), max(xs), max(ys)))
            else:
                heads.append(_head_of(corners))
        elif tag == "line":
            if (ends := _numbers(element, "x1", "y1", "x2", "y2")) is not None:
                x1, y1, x2, y2 = ends
                segments.append(_Segment(x1, y1, x2, y2))
    return boxes, heads, segments


def _defect_for(head: _Arrowhead, boxes: list[_Box], segments: list[_Segment]) -> DrawnDefect | None:
    """What is wrong where *head* points, or None where it arrives properly or only decorates."""
    if any(box.holds(head.tip, slack=_TOUCHING) for box in boxes):
        return None
    crosswise: _Segment | None = None
    touched = False
    for segment in segments:
        distance, along = segment.nearest(head.tip)
        if distance > _TOUCHING:
            continue
        touched = True
        collinear = abs(
            segment.direction[0] * head.direction[0] + segment.direction[1] * head.direction[1]
        ) > _COLLINEAR
        interior = along > _INTERIOR_MARGIN and (segment.length - along) > _INTERIOR_MARGIN
        if not collinear and interior:
            crosswise = segment
    if not touched:
        return DrawnDefect(
            disconnection=Disconnection.REACHES_NOTHING,
            at=head.tip,
            detail="the arrowhead touches no shape and no line, so the flow stops in mid-air",
        )
    if crosswise is not None:
        return DrawnDefect(
            disconnection=Disconnection.REACHES_ANOTHER_ARROW,
            at=head.tip,
            detail=(
                "the arrowhead lands partway along a line running crosswise to it, so the flow "
                "merges into another arrow rather than into a step"
            ),
        )
    return None


def drawn_picture(svg: str) -> DrawnPicture:
    """Read a rendered SVG and report every place its drawing does not connect.

    Raises `ValueError` for input that does not parse as SVG, matching `stamp_svg_banner`: a caller
    holding something that is not a picture has a different problem from a picture with a defect.
    """
    try:
        boxes, heads, segments = _read(svg)
    except Exception as exc:  # noqa: BLE001 — one typed failure for callers
        raise ValueError(f"not a valid SVG document: {exc}") from exc
    defects = [defect for head in heads if (defect := _defect_for(head, boxes, segments)) is not None]
    defects.extend(
        DrawnDefect(
            disconnection=Disconnection.CROSSES_A_SHAPE,
            at=(segment.x1, segment.y1),
            detail=(
                f"the segment ({segment.x1:.0f},{segment.y1:.0f})-({segment.x2:.0f},{segment.y2:.0f}) "
                f"runs through the shape at x{box.left:.0f}-{box.right:.0f} y{box.top:.0f}-{box.bottom:.0f}"
            ),
        )
        for segment in segments
        for box in boxes
        if segment.crosses(box)
    )
    return DrawnPicture(
        defects=tuple(defects), arrowheads_examined=len(heads), shapes_found=len(boxes)
    )
