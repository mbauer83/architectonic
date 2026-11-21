"""What a router is given and what it answers: the scene, the connectors, the routes.

A scene names everything by key: **elements** (shapes with nothing inside them), **boxes** (shapes
other shapes are drawn inside: groupings and elements holding their parts), **text** regions, and
**fixed lines** — lines drawn already that no route is laid along. A connector names its two ends
among the elements and boxes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Side
from src.domain.diagrams.layout.orthogonal import STUB
from src.domain.diagrams.layout.route_quality import END_RUN, LINE_CLEARANCE

#: How far a route keeps from an element it does not end at.
BUFFER: Final = 8.0

#: What one bend costs, in pixels of length a route would rather run than turn.
BEND_PENALTY: Final = 50.0

#: How much more a pixel of run costs for each route already running alongside it: the soft rule that
#: routes spread over the channels there are, rather than all queueing for one nudging cannot widen.
CROWDING: Final = 2.0

#: How far either side of a box's border a candidate line runs, so a route may pass the border at
#: a distance a reader sees as two lines, or cross it.
BORDER_OFFSET: Final = LINE_CLEARANCE + 4.0

#: How far apart nudging places runs that share a line, where there is room; never closer than
#: `LINE_CLEARANCE`.
IDEAL_SEPARATION: Final = 12.0


def run_for(decorated: bool) -> float:
    """How long the straight run out of a port is: a decoration and a clear run, else a stub."""
    return END_RUN if decorated else STUB


@dataclass(frozen=True)
class Connector:
    """One relation to route: its key, its two ends, which ends carry a decoration, what is stated."""

    key: str
    source: str
    target: str
    decorated: tuple[bool, bool] = (True, True)
    #: A port the layout states for an end. Kept as stated; its side is then the only one tried.
    source_port: Port | None = None
    target_port: Port | None = None


@dataclass(frozen=True)
class RoutingScene:
    elements: Mapping[str, Extent]
    boxes: Mapping[str, Extent] = field(default_factory=dict)
    text: Mapping[str, Extent] = field(default_factory=dict)
    fixed_lines: Sequence[Sequence[Point]] = ()

    def extent_of(self, key: str) -> Extent:
        return self.elements[key] if key in self.elements else self.boxes[key]


@dataclass(frozen=True)
class RoutedConnector:
    """A route found: the ports it leaves and arrives by, and its course from port to port."""

    key: str
    source_port: Port
    target_port: Port
    course: tuple[Point, ...]


@dataclass(frozen=True)
class RoutingResult:
    routes: Mapping[str, RoutedConnector]
    #: Connectors no route reaches that keeps every hard rule. Never drawn through something instead.
    unroutable: tuple[str, ...] = ()
    #: Pairs of connector keys whose runs nudging could not separate in the room there was.
    unseparated: tuple[tuple[str, str], ...] = ()


SIDES: Final[tuple[Side, ...]] = (Side.TOP, Side.RIGHT, Side.BOTTOM, Side.LEFT)
