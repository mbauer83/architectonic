"""Which port each end of a searched connector takes, once every connector has a first route.

Ends sharing a side of one element are spread along it (`ports.spread`), each towards the element at
its other end. A connector whose two ends each have their side to themselves is lined up to run
straight where its elements overlap across. A stated port stays as stated.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from src.domain.diagrams.layout.layout_block import Side
from src.domain.diagrams.layout.orthogonal import leaves_level
from src.domain.diagrams.layout.routing.ports import EndOnSide, in_line, spread
from src.domain.diagrams.layout.routing.scene import Connector, RoutedConnector, RoutingScene


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
    return ports
