"""Routes every connector of a scene: ports and stubs, a search each, then nudging.

1. **Sides.** Each connector is searched from every side of its source to every side of its target
   (a stated port: its side only), ports in the middle. The cheapest route decides the sides.
2. **Ports.** Ends sharing a side are spread along it; a connector whose two ends each have their side
   to themselves, facing each other across an overlap, is lined up to run straight. Each connector
   is searched again between its own ports; where that finds nothing, the first route stands.
3. **Nudging** separates what the independent searches laid along one line.

Three kinds of connector are not searched (`special`): a loop, a whole and its part, and two elements
closer than a stub. Which port each end takes once the first routes are found is `spreading`'s.

A connector no route reaches is **unroutable**, reported and never drawn through something instead.

`route_all` with *previous* and *changed* is the quick pass a drag takes: only the connectors of
what moved, and those whose route what moved now lies across, are searched again — between their
ports where those still serve — and only their runs are nudged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Route, Side
from src.domain.diagrams.layout.orthogonal import STUB, half_up
from src.domain.diagrams.layout.routing.lines import Lines, Stubs
from src.domain.diagrams.layout.routing.nudging import nudged
from src.domain.diagrams.layout.routing.ports import OUTWARD_INDEX, Stub, facing_side, in_line, stub_of
from src.domain.diagrams.layout.routing.scene import (
    IDEAL_SEPARATION,
    SIDES,
    Connector,
    RoutedConnector,
    RoutingResult,
    RoutingScene,
    run_for,
)
from src.domain.diagrams.layout.routing.search import DIRECTIONS, REVERSE, Found, Terminal, search
from src.domain.diagrams.layout.routing.shortcuts import improves_detour, shorten
from src.domain.diagrams.layout.routing.special import special
from src.domain.diagrams.layout.routing.spreading import ports_spread
from src.domain.diagrams.layout.routing.visibility import FULL, Passage, Visibility


def _sides_of(port: Port | None, side: Side | None = None) -> tuple[tuple[Side, float], ...]:
    """The ports to try for an end: the stated one; else the middle of *side*, the side its route took
    before; else the middle of every side."""
    if port is not None:
        return ((port.side, port.at),)
    return ((side, 0.5),) if side is not None else tuple((one, 0.5) for one in SIDES)


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


def _usable(stub: Stub, passage: Passage, own: Sequence[Extent], *, arriving: bool) -> bool:
    """Whether *stub* is clear, walked the way the route walks it: out of a source, into a target."""
    a, b = (stub.end, stub.at) if arriving else (stub.at, stub.end)
    return not passage.point_blocked(stub.end) and not passage.step_blocked(a, b, ignoring=own)


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

    def own(self, connector: Connector) -> list[Extent]:
        grown = self.visibility.grown
        return [grown[end] for end in (connector.source, connector.target) if end in grown]

    def still_clear(self, connector: Connector, routed: RoutedConnector) -> bool:
        """Whether a route found before still goes through nothing: what moved may have moved onto it,
        and a route kept through it would be one the full pass does not draw."""
        passage = self.visibility.passage((connector.source, connector.target), bounded=False)
        own = self.own(connector)
        return not any(
            passage.step_blocked(a, b, ignoring=own) for a, b in zip(routed.course, routed.course[1:], strict=False)
        )

    def _stubs(
        self, connector: Connector, which: int, choices: Sequence[tuple[Side, float]], passage: Passage,
    ) -> list[Stub]:
        end = connector.source if which == 0 else connector.target
        extent = self.scene.extent_of(end)
        run, own = run_for(connector.decorated[which]), self.own(connector)
        return [
            stub for side, at in choices
            if _usable(stub := stub_of(extent, side, at, run), passage, own, arriving=which == 1)
        ]

    def searched(
        self, connector: Connector, sources: Sequence[tuple[Side, float]], targets: Sequence[tuple[Side, float]],
        *, lining_up: bool = True, stubs: Stubs | None = None,
    ) -> RoutedConnector | None:
        """The cheapest route between the choices of ports, or None: within the connector's bounds, and
        without them only where no route keeps them.

        With *lining_up*, ports on facing sides are also tried lined up for a straight run; without, the
        ports are as chosen — spread along a side another end shares, which a straight run lined up
        elsewhere would undo. *stubs* are the other connectors' stubs, which no run goes along: nudging
        cannot move a stub, so a run beside one would stay there.
        """
        bounded = self.visibility.passage((connector.source, connector.target))
        for passage in (bounded, bounded.unbounded()):
            found = self._searched_in(connector, sources, targets, passage, lining_up=lining_up, stubs=stubs)
            if found is not None:
                return found
        return None

    def _searched_in(
        self, connector: Connector, sources: Sequence[tuple[Side, float]], targets: Sequence[tuple[Side, float]],
        passage: Passage, *, lining_up: bool, stubs: Stubs | None,
    ) -> RoutedConnector | None:
        starts, goals = self._stubs(connector, 0, sources, passage), self._stubs(connector, 1, targets, passage)
        lined = self._lined_up(connector, sources, targets) if lining_up else ([], [])
        crowded = passage.adding([], self.crowd)
        if (straight := self._straight(connector, [*lined[0], *starts], [*lined[1], *goals], crowded)) is not None:
            return straight
        if not starts or not goals:
            return None
        # A route never crosses its own stubs, nor any other candidate stub of its ends.
        passage = passage.adding(
            [_across_stub(stub) for stub in (*starts, *goals)], self.crowd,
            None if stubs is None else (stubs, connector.key),
        )
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
        own = self.own(connector)
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



def _straightened(points: Sequence[Point]) -> tuple[Point, ...]:
    kept = [points[0]]
    for index in range(1, len(points) - 1):
        before, here, after = kept[-1], points[index], points[index + 1]
        if here == before or (before.x == here.x == after.x) or (before.y == here.y == after.y):
            continue
        kept.append(here)
    return (*kept, points[-1])


#: Far enough to stand for everywhere outside a box.
_FAR = 1.0e7


def _outside(box: Extent | None) -> list[Extent]:
    """Everything outside *box*, as four rectangles: what nudging keeps a route inside its box by."""
    if box is None:
        return []
    return [
        Extent(-_FAR, -_FAR, box.left, _FAR), Extent(box.right, -_FAR, _FAR, _FAR),
        Extent(-_FAR, -_FAR, _FAR, box.top), Extent(-_FAR, box.bottom, _FAR, _FAR),
    ]


def _stub_lines(
    routing: _Routing, connectors: Sequence[Connector],
    ports: Mapping[str, tuple[tuple[Side, float], tuple[Side, float]]], drawn: Sequence[RoutedConnector],
) -> Stubs:
    """Every stub the routes will leave and arrive by: those of the ports chosen, and the first and last
    runs of the routes drawn already. A chosen stub reaches on by the ideal separation, as far as
    nudging may lengthen it."""
    lines = Stubs()
    for connector in connectors:
        if connector.key not in ports:
            continue
        for which, (end, (side, at)) in enumerate(zip((connector.source, connector.target), ports[connector.key],
                                                      strict=True)):
            stub = stub_of(
                routing.scene.extent_of(end), side, at, run_for(connector.decorated[which]) + IDEAL_SEPARATION,
            )
            lines.add(stub.at, stub.end, connector.key)
    for routed in drawn:
        lines.add(routed.course[0], routed.course[1], routed.key)
        lines.add(routed.course[-2], routed.course[-1], routed.key)
    return lines


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
        touched = [
            one for one in ordered
            if one.source in changed or one.target in changed or one.key not in previous
            or not routing.still_clear(one, previous[one.key])
        ]
        kept = {one.key: previous[one.key] for one in ordered if one not in touched and one.key in previous}
        to_route = touched
    for routed in kept.values():
        routing.taken(routed)
    routes: dict[str, RoutedConnector] = {}
    unroutable: list[str] = []
    searched: list[Connector] = []
    first: dict[str, RoutedConnector] = {}
    for connector in to_route:
        made = special(scene, routing.visibility, connector, routing.own(connector))
        if made is True:
            searched.append(connector)
            sides = (_sides_of(connector.source_port), _sides_of(connector.target_port))
            again = previous.get(connector.key) if previous is not None else None
            found = (
                routing.searched(
                    connector, _sides_of(connector.source_port, again.source_port.side),
                    _sides_of(connector.target_port, again.target_port.side),
                )
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
    spread_ports = ports_spread(scene, searched, first)
    stubs = _stub_lines(routing, searched, spread_ports, [*kept.values(), *routes.values()])
    for key, (source, target) in spread_ports.items():
        connector = next(one for one in searched if one.key == key)
        routes[key] = routing.searched(connector, (source,), (target,), lining_up=False, stubs=stubs) or first[key]
        before = routes[key]
        if previous is None and connector.source_port is None and len(before.course) >= 6:
            side = facing_side(scene.extent_of(connector.source), scene.extent_of(connector.target))
            if side is not None and side != source[0]:
                starts = [(side, at) for at in (0.25, 0.5, 0.75)]
                goals = (target,) if connector.target_port else [(s, at) for s in SIDES for at in (0.25, 0.75)]
                alternative = routing.searched(connector, starts, goals, lining_up=False, stubs=stubs)
                if alternative and improves_detour(before, alternative, stubs):
                    routes[key] = alternative
        routing.taken(routes[key])
        # Its first and last runs are fixed to nudging as a stub is: no later route goes along them.
        course = routes[key].course
        stubs.add(course[0], course[1], key)
        stubs.add(course[-2], course[-1], key)
    courses = {key: list(routed.course) for key, routed in {**kept, **routes}.items()}
    obstacles = {
        connector.key: [*routing.visibility.grown.values(), *scene.text.values(),
                        *routing.visibility.passage((connector.source, connector.target)).walls,
                        *_outside(routing.visibility.bounds((connector.source, connector.target)).within)]
        for connector in ordered if connector.key in courses
    }
    moved, unseparated = nudged(
        courses, obstacles, list(scene.boxes.values()), scene.fixed_lines,
        movable=frozenset(routes) if previous is not None and changed is not None else None,
    )
    shorten(moved, searched, routing.visibility, unseparated)
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
