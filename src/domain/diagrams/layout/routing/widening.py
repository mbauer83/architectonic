"""Room for the lines, made once: the arrangement a first layout writes down, its narrow channels widened.

A layout is first written down from the renderer's arrangement, and that arrangement was made for
GraphViz's curves: its gaps between boxes are often narrower than the lines a router lays along them
need (`channels`). Widening opens each such gap by what it lacks, and nothing else:

* every coordinate past the gap's near side moves on by what the gap needs, so a box beyond it moves
  and a box the cut runs through grows, its title band with it. Boxes keep their order, their nesting
  and where they stand relative to each other; an element moves whole and keeps its size;
* the routes are found again and the channels measured again, since lines go where room is made,
  up to `ROUNDS` times.

A pure function of the scene and its connectors, in Python and TypeScript alike, held equal by the
shared fixtures. Once the layout is written down nothing moves that its author did not move: this is
for the first writing only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.domain.diagrams.layout.channels import Channel, too_narrow
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.routing.router import route_all
from src.domain.diagrams.layout.routing.scene import Connector, RoutingScene

#: How many times the routes are found again and the channels widened again.
ROUNDS = 4


class _Spread:
    """Where each coordinate goes, along one axis, once each cut has had its room added past it."""

    def __init__(self, cuts: Mapping[float, int]) -> None:
        self._cuts = sorted(cuts.items())

    def __call__(self, value: float) -> float:
        moved = value
        for at, room in self._cuts:
            if at < value:
                moved += room
        return moved


def _cuts(narrow: Sequence[Channel], across: str) -> dict[float, int]:
    cuts: dict[float, int] = {}
    for channel in narrow:
        if channel.across == across:
            cuts[channel.start] = max(cuts.get(channel.start, 0), channel.wider_by)
    return cuts


def _moved(extent: Extent, x: _Spread, y: _Spread) -> Extent:
    """*extent* moved whole: to where its corner goes, at its size."""
    left, top = x(extent.left), y(extent.top)
    return Extent(left, top, left + extent.width, top + extent.height)


def _stretched(extent: Extent, x: _Spread, y: _Spread) -> Extent:
    """*extent* with each side where it goes: a box a cut runs through grows by the cut's room."""
    return Extent(x(extent.left), y(extent.top), x(extent.right), y(extent.bottom))


def _spread(scene: RoutingScene, narrow: Sequence[Channel]) -> RoutingScene:
    x, y = _Spread(_cuts(narrow, "x")), _Spread(_cuts(narrow, "y"))
    return RoutingScene(
        elements={key: _moved(extent, x, y) for key, extent in scene.elements.items()},
        boxes={key: _stretched(extent, x, y) for key, extent in scene.boxes.items()},
        text={key: _stretched(extent, x, y) for key, extent in scene.text.items()},
        fixed_lines=[[Point(x(point.x), y(point.y)) for point in line] for line in scene.fixed_lines],
    )


def narrow_channels(scene: RoutingScene, connectors: Sequence[Connector]) -> list[Channel]:
    """The channels of *scene* too narrow for the lines its connectors are routed along."""
    result = route_all(scene, connectors)
    courses = [routed.course for routed in result.routes.values()] + [list(line) for line in scene.fixed_lines]
    return too_narrow(scene.boxes, [*scene.elements.values(), *scene.text.values()], courses)


def widened(scene: RoutingScene, connectors: Sequence[Connector]) -> RoutingScene:
    """*scene* with every channel too narrow for its lines opened until they fit, or `ROUNDS` tried."""
    for _round in range(ROUNDS):
        narrow = narrow_channels(scene, connectors)
        if not narrow:
            break
        scene = _spread(scene, narrow)
    return scene
