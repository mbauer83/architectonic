"""Where a connector attaches, and the straight stub it leaves by.

A port is a side and a fraction along it. Its point is put on a whole pixel along the side, and its
stub runs straight out of it for `run_for(decorated)`, its far end rounded outward to a whole pixel:
the search starts and finishes there, so the first and last segments are fixed before it begins and
no bend can sit inside a decoration or right behind it.

Ports sharing one side of one element are spread along it, in the order of what each leads to, so no
two arrive at one point — the soft rule against decorations drawn together.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.diagrams.layout.attachment import fraction
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Side
from src.domain.diagrams.layout.orthogonal import half_up, leaves_level

#: The direction index (see `search.DIRECTIONS`) a route travels leaving each side.
OUTWARD_INDEX: Mapping[Side, int] = {Side.RIGHT: 0, Side.LEFT: 1, Side.BOTTOM: 2, Side.TOP: 3}


@dataclass(frozen=True)
class Stub:
    """A port, the point on the border it stands for, and the far end of the straight run out of it."""

    port: Port
    at: Point
    end: Point


def stub_of(extent: Extent, side: Side, at: float, run: float) -> Stub:
    """The stub out of *extent* on *side*, a fraction *at* along it, running *run* straight out."""
    level = leaves_level(side)
    low, high = (extent.top, extent.bottom) if level else (extent.left, extent.right)
    inner_low, inner_high = math.ceil(low), math.floor(high)
    along = min(max(half_up(low + at * (high - low)), inner_low), inner_high) if inner_low <= inner_high else low
    port = Port(side, fraction((along - low) / (high - low)) if high > low else 0.5)
    point, end = {
        Side.TOP: (Point(along, extent.top), Point(along, math.floor(extent.top - run))),
        Side.BOTTOM: (Point(along, extent.bottom), Point(along, math.ceil(extent.bottom + run))),
        Side.LEFT: (Point(extent.left, along), Point(math.floor(extent.left - run), along)),
        Side.RIGHT: (Point(extent.right, along), Point(math.ceil(extent.right + run), along)),
    }[side]
    return Stub(port, point, end)


@dataclass(frozen=True)
class EndOnSide:
    """One end of one connector on one side of one element, and where along the side its other end lies."""

    connector: str
    which: int
    element: str
    side: Side
    toward: float


def spread(ends: Sequence[EndOnSide]) -> dict[tuple[str, int], float]:
    """A fraction for each end, by (connector, which end): ends sharing a side spread evenly along it,
    ordered by where their other ends lie, ties by connector key."""
    sharing: dict[tuple[str, Side], list[EndOnSide]] = defaultdict(list)
    for end in ends:
        sharing[(end.element, end.side)].append(end)
    spread_at: dict[tuple[str, int], float] = {}
    for group in sharing.values():
        ordered = sorted(group, key=lambda end: (end.toward, end.connector, end.which))
        for position, end in enumerate(ordered, start=1):
            spread_at[(end.connector, end.which)] = position / (len(ordered) + 1)
    return spread_at


def in_line(source: Extent, target: Extent, sides: tuple[Side, Side]) -> tuple[float, float] | None:
    """Fractions that line two facing ports up in one straight run, where the elements overlap across it."""
    level = leaves_level(sides[0])
    if sides[0] == sides[1] or leaves_level(sides[1]) != level:
        return None
    low, high = (
        (max(source.top, target.top), min(source.bottom, target.bottom)) if level
        else (max(source.left, target.left), min(source.right, target.right))
    )
    if high - low < 2:  # noqa: PLR2004 — a whole pixel both can attach at
        return None
    middle = half_up((low + high) / 2)
    return tuple(  # type: ignore[return-value]
        (middle - (extent.top if level else extent.left)) / (extent.height if level else extent.width)
        for extent in (source, target)
    )

def facing_side(source: Extent, target: Extent) -> Side | None:
    """The side directly across a shared horizontal or vertical span from the target."""
    if min(source.right, target.right) > max(source.left, target.left):
        if source.bottom < target.top:
            return Side.BOTTOM
        if target.bottom < source.top:
            return Side.TOP
    if min(source.bottom, target.bottom) > max(source.top, target.top):
        if source.right < target.left:
            return Side.RIGHT
        if target.right < source.left:
            return Side.LEFT
    return None
