"""Which port each end of a searched connector takes, once every connector has a first route.

Ends sharing a side of one element are spread along it (`ports.spread`), each towards the element at
its other end. A connector whose two ends each have their side to themselves is lined up to run
straight where its elements overlap across. A stated port stays as stated.

Two elements facing each other across less than both their stubs can have ports of two different
connectors at one height, whose stubs then run into each other; nudging cannot part them, since a stub
does not move. Such a port is moved along its side by the ideal separation.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from src.domain.diagrams.layout.layout_block import Side
from src.domain.diagrams.layout.orthogonal import leaves_level
from src.domain.diagrams.layout.route_quality import LINE_CLEARANCE
from src.domain.diagrams.layout.routing.ports import EndOnSide, Stub, in_line, spread, stub_of
from src.domain.diagrams.layout.routing.scene import (
    IDEAL_SEPARATION,
    Connector,
    RoutedConnector,
    RoutingScene,
    run_for,
)


def _ends_on_sides(
    scene: RoutingScene, connectors: Sequence[Connector], first: Mapping[str, RoutedConnector],
) -> list[EndOnSide]:
    ends: list[EndOnSide] = []
    for connector in connectors:
        routed = first.get(connector.key)
        if routed is None:
            continue
        for which, (port, stated, other) in enumerate((
            (routed.source_port, connector.source_port, connector.target),
            (routed.target_port, connector.target_port, connector.source),
        )):
            if stated is None:
                centre = scene.extent_of(other).centre
                element = connector.source if which == 0 else connector.target
                toward = centre.y if leaves_level(port.side) else centre.x
                ends.append(EndOnSide(connector.key, which, element, port.side, toward))
    return ends


def ports_spread(
    scene: RoutingScene, connectors: Sequence[Connector], first: Mapping[str, RoutedConnector],
) -> dict[str, tuple[tuple[Side, float], tuple[Side, float]]]:
    """The port each end of *connectors* takes, by connector key, given the sides of its *first* route."""
    ends = _ends_on_sides(scene, connectors, first)
    at = spread(ends)
    sharing = Counter((end.element, end.side) for end in ends)
    alone = {(end.connector, end.which) for end in ends if sharing[(end.element, end.side)] == 1}
    ports: dict[str, tuple[tuple[Side, float], tuple[Side, float]]] = {}
    for connector in connectors:
        routed = first.get(connector.key)
        if routed is None:
            continue
        chosen = [
            (routed.source_port.side, at.get((connector.key, 0), routed.source_port.at)),
            (routed.target_port.side, at.get((connector.key, 1), routed.target_port.at)),
        ]
        if (connector.key, 0) in alone and (connector.key, 1) in alone:
            lined = in_line(
                scene.extent_of(connector.source), scene.extent_of(connector.target),
                (chosen[0][0], chosen[1][0]),
            )
            if lined is not None:
                chosen = [(chosen[0][0], lined[0]), (chosen[1][0], lined[1])]
        ports[connector.key] = (chosen[0], chosen[1])
    return _clear_of_facing(scene, connectors, ports)


def _stub(scene: RoutingScene, connector: Connector, which: int, choice: tuple[Side, float]) -> Stub:
    end = connector.source if which == 0 else connector.target
    return stub_of(scene.extent_of(end), choice[0], choice[1], run_for(connector.decorated[which]))


def _meet(one: Stub, other: Stub) -> bool:
    """Whether two stubs lie along each other closer than the least separation."""
    level = one.at.y == one.end.y
    if level != (other.at.y == other.end.y):
        return False
    at, other_at = (one.at.y, other.at.y) if level else (one.at.x, other.at.x)
    low, high = sorted((one.at.x, one.end.x) if level else (one.at.y, one.end.y))
    other_low, other_high = sorted((other.at.x, other.end.x) if level else (other.at.y, other.end.y))
    return abs(at - other_at) < LINE_CLEARANCE + 1.0 and min(high, other_high) - max(low, other_low) > 0


def _clear_of_facing(
    scene: RoutingScene, connectors: Sequence[Connector],
    ports: dict[str, tuple[tuple[Side, float], tuple[Side, float]]],
) -> dict[str, tuple[tuple[Side, float], tuple[Side, float]]]:
    """*ports* with each unstated port whose stub runs into another connector's moved along its side."""
    ends = [(connector, which) for connector in sorted(connectors, key=lambda one: one.key)
            if connector.key in ports for which in (0, 1)]
    for position, (connector, which) in enumerate(ends):
        if (connector.source_port, connector.target_port)[which] is not None:
            continue
        side, at = ports[connector.key][which]
        extent = scene.extent_of(connector.source if which == 0 else connector.target)
        length = extent.height if leaves_level(side) else extent.width
        others = [_stub(scene, other, other_which, ports[other.key][other_which])
                  for other, other_which in ends[:position] if other.key != connector.key]
        if not others or not any(_meet(_stub(scene, connector, which, (side, at)), one) for one in others):
            continue
        for shift in (IDEAL_SEPARATION, -IDEAL_SEPARATION, 2 * IDEAL_SEPARATION, -2 * IDEAL_SEPARATION):
            moved = at + shift / length if length > 0 else at
            stub = _stub(scene, connector, which, (side, moved))
            if 0.0 < moved < 1.0 and not any(_meet(stub, one) for one in others):
                chosen = list(ports[connector.key])
                chosen[which] = (side, moved)
                ports[connector.key] = (chosen[0], chosen[1])
                break
    return ports
