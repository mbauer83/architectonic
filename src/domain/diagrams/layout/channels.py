"""The gaps between boxes that lines run along, and whether each is wide enough for the lines in it.

A **channel** is the clear gap between two boxes facing each other: two boxes side by side in one
parent, or a box and the border of the box it sits in. The lines a router lays *along* a channel —
not those crossing it — must fit in it at the spacing nudging places them at: `IDEAL_SEPARATION` from
each border and from each other. A channel narrower than that is where lines end up running
along each other or along a border, and no router can repair it: the room is the arrangement's.

One reading of channels, for two askers: the widening that gives a first layout its room
(`routing.widening`), and the picture check that reports a channel still too narrow (W384).
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

    @property
    def width(self) -> float:
        return self.end - self.start

    @property
    def wider_by(self) -> int:
        """How much wider the channel needs to be for its lines, in whole pixels; 0 where they fit."""
        if self.lines == 0:
            return 0
        needed = (self.lines + 1) * IDEAL_SEPARATION
        return max(0, math.ceil(needed - self.width))


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


def channels(
    boxes: Mapping[str, Extent], others: Sequence[Extent], courses: Sequence[Sequence[Point]],
) -> list[Channel]:
    """Every clear channel between *boxes*, with how many of *courses* run along each.

    *others* are the shapes that stand in a channel's way: elements and text.
    """
    parents = parents_of(boxes)
    keys = sorted(boxes)
    found: list[Channel] = []
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
    return [
        Channel(channel.low, channel.high, channel.across, channel.start, channel.end, channel.first, channel.last,
                sum(1 for course in courses if _runs_along(channel, course)))
        for channel in found
        if _clear(_region(channel), (channel.low, channel.high), boxes, others)
    ]


def too_narrow(
    boxes: Mapping[str, Extent], others: Sequence[Extent], courses: Sequence[Sequence[Point]],
) -> list[Channel]:
    """The channels too narrow for the lines that run along them."""
    return [channel for channel in channels(boxes, others, courses) if channel.wider_by > 0]
