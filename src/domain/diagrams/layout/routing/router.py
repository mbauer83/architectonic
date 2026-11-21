"""Routes every connector of a scene: ports and stubs, a search each, then nudging.

1. **Sides.** Each connector is searched from every side of its source to every side of its target
   (a stated port: its side only), ports in the middle. The cheapest route decides the sides.
2. **Ports.** Ends sharing a side are spread along it; a connector whose two ends each have their side
   to themselves, facing each other across an overlap, is lined up to run straight. Each connector
   is searched again between its own ports; where that finds nothing, the first route stands.
3. **Nudging** separates what the independent searches laid along one line.

Three kinds of connector are not searched. One from an element to itself loops round its corner. One
between a box and an element inside it runs straight from the part to the whole's border. One between
two elements closer than a stub, which no route joins keeping I1, is joined the most direct way.

A connector no route reaches is **unroutable**, reported and never drawn through something instead.

`route_all` with *previous* and *changed* is the quick pass a drag takes: only the connectors of
what moved are searched again — between their ports where those still serve — and only their runs
are nudged.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from src.domain.diagrams.layout.attachment import ends_conflict, formed_afresh, fraction, share_along
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Route, Side
from src.domain.diagrams.layout.orthogonal import STUB, course_of, half_up, leaves_level
from src.domain.diagrams.layout.routing.nudging import nudged
from src.domain.diagrams.layout.routing.ports import OUTWARD_INDEX, EndOnSide, Stub, in_line, spread, stub_of
from src.domain.diagrams.layout.routing.scene import (
    SIDES,
    Connector,
    RoutedConnector,
    RoutingResult,
    RoutingScene,
    run_for,
)
from src.domain.diagrams.layout.routing.search import DIRECTIONS, REVERSE, Found, Terminal, search
from src.domain.diagrams.layout.routing.visibility import FULL, Lines, Passage, Visibility


def _sides_of(port: Port | None) -> tuple[tuple[Side, float], ...]:
    return ((port.side, port.at),) if port is not None else tuple((side, 0.5) for side in SIDES)


def _length(a: Point, b: Point) -> float:
    return abs(b.x - a.x) + abs(b.y - a.y)


def _faces(start: Stub, goal: Stub) -> bool:
    """Whether two ports lie in one line, the start's stub pointing at the goal, a stub apart at least."""
    dx, dy = goal.at.x - start.at.x, goal.at.y - start.at.y
    out_x, out_y = DIRECTIONS[OUTWARD_INDEX[start.port.side]]
    return (dx * out_y == 0 and dy * out_x == 0) and dx * out_x + dy * out_y >= STUB


def _across_stub(stub: Stub) -> Extent:
    """A thin rectangle along a stub, short of its far end: a route crossing it is blocked, one leaving it is not."""
    a, b = stub.at, stub.end
    if a.x == b.x:
        top, bottom = (a.y, b.y - 1.0) if b.y > a.y else (b.y + 1.0, a.y)
        return Extent(a.x - 1.0, top, a.x + 1.0, bottom)
    left, right = (a.x, b.x - 1.0) if b.x > a.x else (b.x + 1.0, a.x)
    return Extent(left, a.y - 1.0, right, a.y + 1.0)


def _usable(stub: Stub, passage: Passage, own: Sequence[Extent]) -> bool:
    return not passage.point_blocked(stub.end) and not passage.step_blocked(stub.at, stub.end, ignoring=own)


class _Routing:
    def __init__(self, scene: RoutingScene) -> None:
        self.scene = scene
        self.visibility = Visibility(scene)
        #: The routes found so far, which later searches pay to run alongside.
        self.crowd = Lines()
        for line in scene.fixed_lines:
            for a, b in zip(line, line[1:], strict=False):
                self.crowd.add(a, b)

    def taken(self, routed: RoutedConnector) -> None:
        for a, b in zip(routed.course, routed.course[1:], strict=False):
            self.crowd.add(a, b)

    def _own(self, connector: Connector) -> list[Extent]:
        grown = self.visibility.grown
        return [grown[end] for end in (connector.source, connector.target) if end in grown]

    def _stubs(
        self, connector: Connector, which: int, choices: Sequence[tuple[Side, float]], passage: Passage,
    ) -> list[Stub]:
        end = connector.source if which == 0 else connector.target
        extent = self.scene.extent_of(end)
        run, own = run_for(connector.decorated[which]), self._own(connector)
        return [stub for side, at in choices if _usable(stub := stub_of(extent, side, at, run), passage, own)]

    def searched(
        self, connector: Connector, sources: Sequence[tuple[Side, float]], targets: Sequence[tuple[Side, float]],
        *, lining_up: bool = True,
    ) -> RoutedConnector | None:
        """The cheapest route between the choices of ports, or None. With *lining_up*, ports on facing
        sides are also tried lined up for a straight run; without, the ports are as chosen — spread
        along a side another end shares, which a straight run lined up elsewhere would undo."""
        passage = self.visibility.passage((connector.source, connector.target))
        starts, goals = self._stubs(connector, 0, sources, passage), self._stubs(connector, 1, targets, passage)
        lined = self._lined_up(connector, sources, targets) if lining_up else ([], [])
        crowded = passage.adding([], self.crowd)
        if (straight := self._straight(connector, [*lined[0], *starts], [*lined[1], *goals], crowded)) is not None:
            return straight
        if not starts or not goals:
            return None
        # A route never crosses its own stubs, nor any other candidate stub of its ends.
        passage = passage.adding([_across_stub(stub) for stub in (*starts, *goals)], self.crowd)
        found = search(
            [Terminal(stub.end, OUTWARD_INDEX[stub.port.side], tag) for tag, stub in enumerate(starts)],
            [Terminal(stub.end, REVERSE[OUTWARD_INDEX[stub.port.side]], tag) for tag, stub in enumerate(goals)],
            passage, self.visibility.graph,
        )
        return None if found is None else self._as_routed(connector, found, starts, goals)

    def _lined_up(
        self, connector: Connector, sources: Sequence[tuple[Side, float]], targets: Sequence[tuple[Side, float]],
    ) -> tuple[list[Stub], list[Stub]]:
        """Ports on facing sides lined up across where the two elements overlap, for a straight run.

        Not for a stated port, which stays where it is stated.
        """
        source, target = self.scene.extent_of(connector.source), self.scene.extent_of(connector.target)
        starts: list[Stub] = []
        goals: list[Stub] = []
        if connector.source_port is not None or connector.target_port is not None:
            return starts, goals
        for side, _at in sources:
            for other, _other_at in targets:
                if (lined := in_line(source, target, (side, other))) is not None:
                    # A straight run has no bend, so it needs no stub; its ports are all it is.
                    starts.append(stub_of(source, side, lined[0], 0.0))
                    goals.append(stub_of(target, other, lined[1], 0.0))
        return starts, goals

    def _straight(
        self, connector: Connector, starts: Sequence[Stub], goals: Sequence[Stub], passage: Passage,
    ) -> RoutedConnector | None:
        """The one straight run between two facing ports in line, where it is clear: it has no bend to
        need a stub before, and two stubs between ends closer than both would only tangle."""
        own = self._own(connector)
        straight = [
            (start, goal) for start in starts for goal in goals
            if REVERSE[OUTWARD_INDEX[start.port.side]] == OUTWARD_INDEX[goal.port.side]
            and _faces(start, goal) and not passage.step_blocked(start.at, goal.at, ignoring=own)
            and passage.crowding(start.at, goal.at) < FULL
        ]
        if not straight:
            return None
        start, goal = min(straight, key=lambda pair: _length(pair[0].at, pair[1].at))
        return RoutedConnector(connector.key, start.port, goal.port, (start.at, goal.at))

    @staticmethod
    def _as_routed(
        connector: Connector, found: Found, starts: Sequence[Stub], goals: Sequence[Stub],
    ) -> RoutedConnector:
        start, goal = starts[found.start], goals[found.goal]
        course = _straightened([start.at, *found.points, goal.at])
        return RoutedConnector(connector.key, start.port, goal.port, course)

    def special(self, connector: Connector) -> RoutedConnector | None | bool:
        """The route of a connector that is not searched; True where it is to be searched."""
        source, target = self.scene.extent_of(connector.source), self.scene.extent_of(connector.target)
        if connector.source == connector.target:
            return _around_itself(connector, source)
        if source.encloses(target) or target.encloses(source):
            return self._whole_to_part(connector, source, target)
        if ends_conflict(source, target):
            made = formed_afresh(Route(), source, target)
            course = course_of(made, source, target)
            if made.source is not None and made.target is not None and course is not None:
                return RoutedConnector(connector.key, made.source, made.target, course)
        return True

    def _whole_to_part(self, connector: Connector, source: Extent, target: Extent) -> RoutedConnector | None:
        whole_is_source = source.encloses(target)
        whole, part = (source, target) if whole_is_source else (target, source)
        part_key = connector.target if whole_is_source else connector.source
        passage = self.visibility.passage((part_key, part_key))
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
            if passage.step_blocked(stub.at, border, ignoring=self._own(connector)):
                continue
            level = leaves_level(side)
            whole_port = Port(side, fraction(share_along(whole, border.y if level else border.x, level=level)))
            if whole_is_source:
                return RoutedConnector(connector.key, whole_port, stub.port, (border, stub.at))
            return RoutedConnector(connector.key, stub.port, whole_port, (stub.at, border))
        return None


def _straightened(points: Sequence[Point]) -> tuple[Point, ...]:
    kept = [points[0]]
    for index in range(1, len(points) - 1):
        before, here, after = kept[-1], points[index], points[index + 1]
        if here == before or (before.x == here.x == after.x) or (before.y == here.y == after.y):
            continue
        kept.append(here)
    return (*kept, points[-1])


def _around_itself(connector: Connector, extent: Extent) -> RoutedConnector:
    """A connector from an element to itself: out of its right side, round the corner, in at its bottom."""
    leaving = stub_of(extent, Side.RIGHT, 0.7, run_for(connector.decorated[0]))
    arriving = stub_of(extent, Side.BOTTOM, 0.7, run_for(connector.decorated[1]))
    corner = Point(leaving.end.x, arriving.end.y)
    course = (leaving.at, leaving.end, corner, arriving.end, arriving.at)
    return RoutedConnector(connector.key, leaving.port, arriving.port, course)


def _ends_on_sides(
    routing: _Routing, connectors: Sequence[Connector], first: Mapping[str, RoutedConnector],
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
                centre = routing.scene.extent_of(other).centre
                element = connector.source if which == 0 else connector.target
                toward = centre.y if leaves_level(port.side) else centre.x
                ends.append(EndOnSide(connector.key, which, element, port.side, toward))
    return ends


def _ports_spread(
    routing: _Routing, connectors: Sequence[Connector], first: Mapping[str, RoutedConnector],
) -> dict[str, tuple[tuple[Side, float], tuple[Side, float]]]:
    ends = _ends_on_sides(routing, connectors, first)
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
                routing.scene.extent_of(connector.source), routing.scene.extent_of(connector.target),
                (chosen[0][0], chosen[1][0]),
            )
            if lined is not None:
                chosen = [(chosen[0][0], lined[0]), (chosen[1][0], lined[1])]
        ports[connector.key] = (chosen[0], chosen[1])
    return ports


def route_all(
    scene: RoutingScene, connectors: Sequence[Connector], *,
    previous: Mapping[str, RoutedConnector] | None = None, changed: frozenset[str] | None = None,
) -> RoutingResult:
    """Every connector's route, the unroutable ones, and what nudging could not separate."""
    routing = _Routing(scene)
    ordered = sorted(connectors, key=lambda connector: connector.key)
    kept: dict[str, RoutedConnector] = {}
    to_route = ordered
    if previous is not None and changed is not None:
        touched = [one for one in ordered if one.source in changed or one.target in changed or one.key not in previous]
        kept = {one.key: previous[one.key] for one in ordered if one not in touched and one.key in previous}
        to_route = touched
    for routed in kept.values():
        routing.taken(routed)
    routes: dict[str, RoutedConnector] = {}
    unroutable: list[str] = []
    searched: list[Connector] = []
    first: dict[str, RoutedConnector] = {}
    for connector in to_route:
        made = routing.special(connector)
        if made is True:
            searched.append(connector)
            sides = (_sides_of(connector.source_port), _sides_of(connector.target_port))
            again = previous.get(connector.key) if previous is not None else None
            found = (
                routing.searched(connector, ((again.source_port.side, 0.5),), ((again.target_port.side, 0.5),))
                if again is not None else None
            ) or routing.searched(connector, *sides)
            if found is None:
                unroutable.append(connector.key)
            else:
                first[connector.key] = found
        elif made is None or made is False:
            unroutable.append(connector.key)
        else:
            routes[connector.key] = made
            routing.taken(made)
    for key, (source, target) in _ports_spread(routing, searched, first).items():
        connector = next(one for one in searched if one.key == key)
        routes[key] = routing.searched(connector, (source,), (target,), lining_up=False) or first[key]
        routing.taken(routes[key])
    courses = {key: list(routed.course) for key, routed in {**kept, **routes}.items()}
    obstacles = {
        connector.key: [*routing.visibility.grown.values(), *scene.text.values(),
                        *routing.visibility.passage((connector.source, connector.target)).walls]
        for connector in ordered if connector.key in courses
    }
    moved, unseparated = nudged(
        courses, obstacles, list(scene.boxes.values()), scene.fixed_lines,
        movable=frozenset(routes) if previous is not None and changed is not None else None,
    )
    every = {**kept, **routes}
    return RoutingResult(
        routes={
            key: RoutedConnector(key, every[key].source_port, every[key].target_port, tuple(moved[key]))
            for key in sorted(every)
        },
        unroutable=tuple(unroutable),
        unseparated=tuple(unseparated),
    )


def as_route(routed: RoutedConnector) -> Route:
    """A routed connector as a layout states a route: its ports, and the points it turns at."""
    return Route(
        routed.source_port, routed.target_port,
        tuple((half_up(point.x), half_up(point.y)) for point in routed.course[1:-1]),
    )


def rerouted(scene: RoutingScene, connector: Connector) -> Route | None:
    """One connector routed again between the ports it states, as the arrow a move made cross an
    element (I5) is; None where no route between them keeps the rules."""
    result = route_all(scene, [connector])
    routed = result.routes.get(connector.key)
    return as_route(routed) if routed is not None else None
