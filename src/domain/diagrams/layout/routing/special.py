"""The connectors that are not searched, and the route each takes instead.

One from an element to itself loops round its corner. One between a box and an element inside it runs
straight from the part to the whole's border. One between two elements closer than a stub, which no
route joins keeping I1, is joined the most direct way.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.diagrams.layout.attachment import ends_conflict, formed_afresh, fraction, share_along
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Route, Side
from src.domain.diagrams.layout.orthogonal import course_of, leaves_level
from src.domain.diagrams.layout.routing.ports import stub_of
from src.domain.diagrams.layout.routing.scene import SIDES, Connector, RoutedConnector, RoutingScene, run_for
from src.domain.diagrams.layout.routing.visibility import Visibility


def special(
    scene: RoutingScene, visibility: Visibility, connector: Connector, own: Sequence[Extent],
) -> RoutedConnector | None | bool:
    """The route of a connector that is not searched; True where it is to be searched. *own* is what
    its ends block, grown."""
    source, target = scene.extent_of(connector.source), scene.extent_of(connector.target)
    if connector.source == connector.target:
        return _around_itself(connector, source)
    if source.encloses(target) or target.encloses(source):
        return _whole_to_part(visibility, connector, source, target, own)
    if ends_conflict(source, target):
        made = formed_afresh(Route(), source, target)
        course = course_of(made, source, target)
        if made.source is not None and made.target is not None and course is not None:
            return RoutedConnector(connector.key, made.source, made.target, course)
    return True


def _whole_to_part(
    visibility: Visibility, connector: Connector, source: Extent, target: Extent, own: Sequence[Extent],
) -> RoutedConnector | None:
    whole_is_source = source.encloses(target)
    whole, part = (source, target) if whole_is_source else (target, source)
    part_key = connector.target if whole_is_source else connector.source
    passage = visibility.passage((part_key, part_key), bounded=False)
    gaps = {
        Side.TOP: part.top - whole.top, Side.BOTTOM: whole.bottom - part.bottom,
        Side.LEFT: part.left - whole.left, Side.RIGHT: whole.right - part.right,
    }
    for side in sorted(SIDES, key=lambda one: (gaps[one], SIDES.index(one))):
        stub = stub_of(part, side, 0.5, 0.0)
        border = {
            Side.TOP: Point(stub.at.x, whole.top), Side.BOTTOM: Point(stub.at.x, whole.bottom),
            Side.LEFT: Point(whole.left, stub.at.y), Side.RIGHT: Point(whole.right, stub.at.y),
        }[side]
        if passage.step_blocked(stub.at, border, ignoring=own):
            continue
        level = leaves_level(side)
        whole_port = Port(side, fraction(share_along(whole, border.y if level else border.x, level=level)))
        if whole_is_source:
            return RoutedConnector(connector.key, whole_port, stub.port, (border, stub.at))
        return RoutedConnector(connector.key, stub.port, whole_port, (stub.at, border))
    return None


def _around_itself(connector: Connector, extent: Extent) -> RoutedConnector:
    """A connector from an element to itself: out of its right side, round the corner, in at its bottom."""
    leaving = stub_of(extent, Side.RIGHT, 0.7, run_for(connector.decorated[0]))
    arriving = stub_of(extent, Side.BOTTOM, 0.7, run_for(connector.decorated[1]))
    corner = Point(leaving.end.x, arriving.end.y)
    course = (leaving.at, leaving.end, corner, arriving.end, arriving.at)
    return RoutedConnector(connector.key, leaving.port, arriving.port, course)
