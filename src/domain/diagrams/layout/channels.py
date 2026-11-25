"""The gaps between boxes that lines run along, and whether each is wide enough for the lines in it.

A **channel** is the clear gap between two boxes facing each other: two boxes side by side in one
parent, or a box — or an element — and the border of the box it sits in. The lines a router lays
*along* a channel — not those crossing it — must fit in it at the spacing nudging places them at:
`IDEAL_SEPARATION` from each border and from each other. And a line that ends on a shape facing the
gap leaves it by its straight run — `END_RUN` behind an arrowhead — which must end inside the gap
with room to turn: otherwise the run into an arrowhead starts outside the box holding its target.
A channel narrower than that is where lines end up running along each other or along a border, and
no router can repair it: the room is the arrangement's.

The picture check that reports a channel too narrow for its lines (W384) reads channels here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.routing.scene import IDEAL_SEPARATION

#: How much of a channel's length a run must share to count as running along it, and how far two
#: shapes must overlap to stand in a channel's way.
_SHARED = 1.0

#: How far a gap may fall short and still fit: the rounding of a layout to whole pixels.
_ROUNDING = 1.0


@dataclass(frozen=True)
class Channel:
    """The gap between two boxes, by their keys, the one with the lower coordinate first.

    *across* says which coordinate the gap spans: ``"x"`` for boxes side by side, whose lines run
    upright in it, ``"y"`` for boxes one above the other, whose lines run level.
    """

    low: str
    high: str
    across: str
    #: Where the gap starts and ends, across it.
    start: float
    end: float
    #: Where it starts and ends, along it.
    first: float
    last: float
    #: How many lines run along it.
    lines: int = 0
    #: The longest straight run out of a shape facing it, of a line ending there; 0 for none.
    run: float = 0.0

    @property
    def width(self) -> float:
        return self.end - self.start

    @property
    def wider_by(self) -> int:
        """How much wider the channel needs to be for its lines and the runs out of it, in whole pixels;
        0 where they fit. A pixel's rounding is allowed, as a layout states whole pixels."""
        along = (self.lines + 1) * IDEAL_SEPARATION if self.lines else 0.0
        out_of = self.run + IDEAL_SEPARATION if self.run else 0.0
        return max(0, math.ceil(max(along, out_of) - self.width - _ROUNDING))


def parents_of(boxes: Mapping[str, Extent]) -> dict[str, str | None]:
    """Each box's parent: the smallest other box that encloses it, or None at the top."""
    parents: dict[str, str | None] = {}
    for key, box in boxes.items():
        around = [
            (other.width * other.height, other_key) for other_key, other in boxes.items()
            if other_key != key and other.encloses(box) and other != box
        ]
        parents[key] = min(around)[1] if around else None
    return parents


def _region(channel: Channel) -> Extent:
    if channel.across == "x":
        return Extent(channel.start, channel.first, channel.end, channel.last)
    return Extent(channel.first, channel.start, channel.last, channel.end)


def _between(low: str, high: str, lower: Extent, upper: Extent, across: str) -> Channel | None:
    """The channel from *lower*'s far side to *upper*'s near side across *across*, where they face."""
    if across == "x":
        start, end, first, last = lower.right, upper.left, max(lower.top, upper.top), min(lower.bottom, upper.bottom)
    else:
        start, end, first, last = lower.bottom, upper.top, max(lower.left, upper.left), min(lower.right, upper.right)
    return Channel(low, high, across, start, end, first, last) if end > start and last - first > _SHARED else None


def _inside(child: str, parent: str, inner: Extent, outer: Extent) -> list[Channel]:
    """The four channels between a box and the border of the box it sits in."""
    found = [
        Channel(parent, child, "x", outer.left, inner.left, inner.top, inner.bottom),
        Channel(child, parent, "x", inner.right, outer.right, inner.top, inner.bottom),
        Channel(parent, child, "y", outer.top, inner.top, inner.left, inner.right),
        Channel(child, parent, "y", inner.bottom, outer.bottom, inner.left, inner.right),
    ]
    return [channel for channel in found if channel.width > 0 and channel.last - channel.first > _SHARED]


def _clear(region: Extent, keys: tuple[str, str], boxes: Mapping[str, Extent], others: Sequence[Extent]) -> bool:
    """Whether nothing but the two boxes and what holds them stands in *region*."""
    standing = [*(box for key, box in boxes.items() if key not in keys and not box.encloses(region)), *others]
    return not any(
        (shared := region.overlap_with(shape)) is not None and shared.width > _SHARED and shared.height > _SHARED
        for shape in standing
    )


def _runs_along(channel: Channel, course: Sequence[Point]) -> bool:
    for a, b in zip(course, course[1:], strict=False):
        upright = a.x == b.x and a.y != b.y
        level = a.y == b.y and a.x != b.x
        if channel.across == "x" and upright and channel.start < a.x < channel.end:
            low, high = min(a.y, b.y), max(a.y, b.y)
        elif channel.across == "y" and level and channel.start < a.y < channel.end:
            low, high = min(a.x, b.x), max(a.x, b.x)
        else:
            continue
        if min(high, channel.last) - max(low, channel.first) > _SHARED:
            return True
    return False


def _run_out_of(channel: Channel, shapes: Mapping[str, Extent], ends: Sequence[tuple[Point, float]]) -> float:
    """The longest run of a line ending on a shape that faces *channel*: its edge on the gap, not one
    round it (a box's border around a member faces away from the gap)."""
    region = _region(channel)
    edges = [
        edge for key, edge in ((channel.low, channel.start), (channel.high, channel.end))
        if not shapes[key].encloses(region)
    ]
    runs = [
        run for point, run in ends for edge in edges
        if abs((point.x if channel.across == "x" else point.y) - edge) <= _SHARED
        and channel.first <= (point.y if channel.across == "x" else point.x) <= channel.last
    ]
    return max(runs, default=0.0)


def _members(boxes: Mapping[str, Extent], members: Mapping[str, Extent]) -> list[Channel]:
    """The channels between each element and the border of the smallest box holding it."""
    found: list[Channel] = []
    for key in sorted(members):
        holding = [(box.width * box.height, box_key) for box_key, box in boxes.items()
                   if box.encloses(members[key]) and box != members[key]]
        if holding:
            parent = min(holding)[1]
            found += _inside(key, parent, members[key], boxes[parent])
    return found


def channels(
    boxes: Mapping[str, Extent], others: Sequence[Extent], courses: Sequence[Sequence[Point]],
    members: Mapping[str, Extent] | None = None, ends: Sequence[tuple[Point, float]] = (),
) -> list[Channel]:
    """Every clear channel between *boxes*, and between *members* and their boxes, with how many of
    *courses* run along each and the longest of *ends* — a line's end and its straight run — out of it.

    *others* are the shapes that stand in a channel's way: elements and text.
    """
    members = members or {}
    parents = parents_of(boxes)
    keys = sorted(boxes)
    found: list[Channel] = _members(boxes, members)
    for index, one in enumerate(keys):
        if (parent := parents[one]) is not None:
            found += _inside(one, parent, boxes[one], boxes[parent])
        for other in keys[index + 1 :]:
            if parents[other] != parents[one]:
                continue
            for across in ("x", "y"):
                for low, high in ((one, other), (other, one)):
                    if (channel := _between(low, high, boxes[low], boxes[high], across)) is not None:
                        found.append(channel)
    shapes = {**members, **boxes}
    return [
        Channel(channel.low, channel.high, channel.across, channel.start, channel.end, channel.first, channel.last,
                sum(1 for course in courses if _runs_along(channel, course)), _run_out_of(channel, shapes, ends))
        for channel in found
        if _clear(_region(channel), (channel.low, channel.high), boxes,
                  [other for other in others if other not in (shapes[channel.low], shapes[channel.high])])
    ]


def too_narrow(
    boxes: Mapping[str, Extent], others: Sequence[Extent], courses: Sequence[Sequence[Point]],
    members: Mapping[str, Extent] | None = None, ends: Sequence[tuple[Point, float]] = (),
) -> list[Channel]:
    """The channels too narrow for the lines that run along them, or the runs out of them."""
    return [channel for channel in channels(boxes, others, courses, members, ends) if channel.wider_by > 0]
