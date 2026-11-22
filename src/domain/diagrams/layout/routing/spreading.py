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
from src.domain.diagrams.layout.routing.lines import Lines
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


def _meets_earlier(stub: Stub, earlier: Lines) -> bool:
    level = stub.at.y == stub.end.y
    low, high = sorted((stub.at.x, stub.end.x) if level else (stub.at.y, stub.end.y))
    return any(min(high, end) > max(low, start)
               for _, start, end in earlier.spans_near(stub.at, stub.end, LINE_CLEARANCE + 1.0))


def _clear_of_facing(
    scene: RoutingScene, connectors: Sequence[Connector],
    ports: dict[str, tuple[tuple[Side, float], tuple[Side, float]]],
) -> dict[str, tuple[tuple[Side, float], tuple[Side, float]]]:
    """Keep both stubs of each connector clear of previously placed connectors."""
    earlier = Lines()
    for connector in sorted(connectors, key=lambda one: one.key):
        if connector.key not in ports:
            continue
        chosen = list(ports[connector.key])
        placed = []
        for which, (side, at) in enumerate(chosen):
            stub = _stub(scene, connector, which, (side, at))
            stated = (connector.source_port, connector.target_port)[which]
            if stated is None and _meets_earlier(stub, earlier):
                extent = scene.extent_of(connector.source if which == 0 else connector.target)
                length = extent.height if leaves_level(side) else extent.width
                for shift in (1, -1, 2, -2):
                    moved = at + shift * IDEAL_SEPARATION / length if length > 0 else at
                    trial = _stub(scene, connector, which, (side, moved))
                    if 0.0 < moved < 1.0 and not _meets_earlier(trial, earlier):
                        chosen[which], stub = (side, moved), trial
                        break
            placed.append(stub)
        ports[connector.key] = (chosen[0], chosen[1])
        for stub in placed:
            earlier.add(stub.at, stub.end)
    return ports
