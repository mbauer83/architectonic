"""Decides what a layout leaves to the router: which sides a relation attaches on, where along them, and its bends.

Three steps, each over every undecided relation at once, because each depends on the others' answers:

1. **Sides** — the pair that looks cheapest, counting how crowded each side already is. Only the
   pairs that face the other end are compared, and by an estimate rather than a trial route: on a
   view of a few hundred elements sixteen searched trials per relation are the whole budget.
2. **Ports** — the ends sharing one side of one element are spread along it, in the order of what
   they lead to, so they do not cross on the way out and no two arrive at one point; and an end at a
   box is kept off the box's title band.
3. **Bends** — each relation routed around every element and every text, keeping apart from those
   already routed. A relation that found its way only from other sides has its ends spread again
   with the ones it now shares a side with.

Two elements closer than a stub have no route that keeps I1; they are joined the most direct way.
A port the layout states is kept; so is everything about a relation whose two ports are stated.
`rerouted` is the third step alone, for the arrow a move made cross an element (I5).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from src.domain.diagrams.layout.attachment import ends_conflict, formed_afresh, fraction, share_along
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Route, Side
from src.domain.diagrams.layout.orthogonal import STUB, course_of, half_up, leaves_level
from src.infrastructure.rendering.layout.router import Leniency, Routed, Router, Surroundings

#: What attaching on a side another relation already uses costs when sides are chosen.
_CROWDED = 90.0

#: An end: the element it is at, the side it attaches on, and the element at the relation's other end.
EndOnSide = tuple[str, Side, str]


@dataclass(frozen=True)
class Undecided:
    """One relation the router decides: its key, its two ends, and whatever the layout does state."""

    key: str
    source: str
    target: str
    stated: Route = Route()
    #: Which ends carry a decoration — an arrowhead, a diamond, a dot — and so need a straight run.
    decorated: tuple[bool, bool] = (True, True)


def _facing_sides(extent: Extent, other: Extent) -> list[Side]:
    """The sides of *extent* that look towards *other*, the one across the wider gap first."""
    across = Side.RIGHT if other.centre.x > extent.centre.x else Side.LEFT
    down = Side.BOTTOM if other.centre.y > extent.centre.y else Side.TOP
    gap_x = max(other.left - extent.right, extent.left - other.right)
    gap_y = max(other.top - extent.bottom, extent.top - other.bottom)
    return [across, down] if gap_x > gap_y else [down, across]


def _passable(extents: Mapping[str, Extent], obstacles: Mapping[str, Extent], ends: tuple[str, str]) -> frozenset[str]:
    """The elements a relation may cross: those one of its ends is drawn inside. Never what an end holds."""
    own = [extents[end] for end in ends if end in extents]
    return frozenset(
        key for key, extent in obstacles.items()
        if key not in ends and any(extent.encloses(end) for end in own)
    )


def _walls(extents: Mapping[str, Extent], obstacles: Mapping[str, Extent], ends: tuple[str, str]) -> list[Extent]:
    """The boxes a relation may not enter: each that holds neither of its ends, and an end that is a box."""
    own = [extents[end] for end in ends if end in extents]
    return [
        box for key, box in extents.items()
        if key not in obstacles and (key in ends or not any(box.encloses(end) for end in own))
    ]


def _in_line(source: Extent, target: Extent, sides: tuple[Side, Side]) -> tuple[Port, Port] | None:
    """Two ports on facing sides that meet in one straight run, where the two elements overlap across it."""
    level = leaves_level(sides[0])
    if sides[0] == sides[1] or leaves_level(sides[1]) != level:
        return None
    low, high = (
        (max(source.top, target.top), min(source.bottom, target.bottom)) if level
        else (max(source.left, target.left), min(source.right, target.right))
    )
    if high <= low:
        return None
    middle = (low + high) / 2
    return (
        Port(sides[0], fraction(share_along(source, middle, level=level))),
        Port(sides[1], fraction(share_along(target, middle, level=level))),
    )


def _as_bends(routed: Routed) -> tuple[tuple[int, int], ...]:
    return tuple((half_up(point.x), half_up(point.y)) for point in routed.bends)


def _around_itself(extent: Extent) -> Route:
    """A relation from an element to itself: out of its right side, round the corner, in at the bottom."""
    out, under = half_up(extent.right + 2 * STUB), half_up(extent.bottom + 2 * STUB)
    leaving, arriving = Port(Side.RIGHT, 0.7), Port(Side.BOTTOM, 0.7)
    level, upright = extent.top + 0.7 * extent.height, extent.left + 0.7 * extent.width
    return Route(leaving, arriving, ((out, half_up(level)), (out, under), (half_up(upright), under)))


def _both_ways(relation: Undecided) -> tuple[tuple[str, str], tuple[str, str]]:
    return (relation.source, relation.target), (relation.target, relation.source)


class RelationRouting:
    """The routing of one arrangement: what is already settled, and what the router is asked to decide."""

    def __init__(
        self, extents: Mapping[str, Extent], obstacles: Mapping[str, Extent],
        around: Surroundings | None = None, bands: Mapping[str, Extent] | None = None,
    ) -> None:
        """*extents* is everything a relation may end at; *obstacles* the elements none may cross.

        *around* is the text and the borders every route keeps clear of; *bands* the title band of each
        box, by its alias, which a relation ending at that box never attaches beside.
        """
        self._extents = extents
        self._obstacles = obstacles
        self._bands = bands or {}
        self._router = Router(obstacles, around)

    def keep_apart_from(self, course: Sequence[Point]) -> None:
        self._router.keep_apart_from(course)

    def _off_the_band(self, alias: str, port: Port) -> Port:
        """*port*, moved down a side past the box's title band where it would attach beside it."""
        band, extent = self._bands.get(alias), self._extents[alias]
        if band is None or not leaves_level(port.side) or extent.height <= 0:
            return port
        below = (band.bottom - extent.top + STUB) / extent.height
        return Port(port.side, fraction(max(port.at, below))) if below < 1 else port

    def _sides_chosen(self, undecided: Sequence[Undecided]) -> dict[str, tuple[Side, Side]]:
        load: dict[tuple[str, Side], int] = defaultdict(int)
        chosen: dict[str, tuple[Side, Side]] = {}

        def span(relation: Undecided) -> float:
            return self._extents[relation.source].centre.distance_to(self._extents[relation.target].centre)

        # The longest first: they have the fewest good ways, so they choose before a side fills.
        for relation in sorted(undecided, key=lambda one: (-span(one), one.key)):
            source, target = self._extents[relation.source], self._extents[relation.target]
            passable = _passable(self._extents, self._obstacles, (relation.source, relation.target))
            stated = relation.stated
            from_sides = [stated.source.side] if stated.source else _facing_sides(source, target)
            to_sides = [stated.target.side] if stated.target else _facing_sides(target, source)
            best, pair = float("inf"), (from_sides[0], to_sides[0])
            for leaving in from_sides:
                for arriving in to_sides:
                    cost = self._router.estimate(
                        source, Port(leaving, 0.5), target, Port(arriving, 0.5), passable=passable
                    ) + _CROWDED * (load[(relation.source, leaving)] + load[(relation.target, arriving)])
                    if cost < best:
                        best, pair = cost, (leaving, arriving)
            chosen[relation.key] = pair
            load[(relation.source, pair[0])] += 1
            load[(relation.target, pair[1])] += 1
        return chosen

    def _spread(self, ends: Mapping[tuple[str, int], EndOnSide]) -> dict[tuple[str, int], Port]:
        """A port for each end, by (relation, which end): ends sharing a side spread along it in the
        order of what they lead to, and kept off a title band."""
        sharing: dict[tuple[str, Side], list[tuple[float, str, int]]] = defaultdict(list)
        for (key, which), (here, side, there) in ends.items():
            other = self._extents[there].centre
            sharing[(here, side)].append((other.y if leaves_level(side) else other.x, key, which))
        return {
            (key, which): self._off_the_band(element, Port(side, fraction(position / (len(group) + 1))))
            for (element, side), group in sharing.items()
            for position, (_along, key, which) in enumerate(sorted(group), start=1)
        }

    def _ports_spread(
        self, undecided: Sequence[Undecided], sides: Mapping[str, tuple[Side, Side]]
    ) -> dict[str, tuple[Port, Port]]:
        """Each undecided end's port, spread along its side. A relation whose ends each have their side
        to themselves, and whose elements overlap across the gap, runs straight."""
        ends = {
            (relation.key, which): (here, sides[relation.key][which], there)
            for relation in undecided
            for which, (here, there) in enumerate(_both_ways(relation))
        }
        spread = self._spread(ends)
        on_side: dict[tuple[str, Side], int] = defaultdict(int)
        for here, side, _there in ends.values():
            on_side[(here, side)] += 1
        for relation in undecided:
            alone = all(on_side[ends[(relation.key, which)][:2]] == 1 for which in (0, 1))
            straight = alone and _in_line(
                self._extents[relation.source], self._extents[relation.target], sides[relation.key]
            )
            if straight:
                spread[(relation.key, 0)], spread[(relation.key, 1)] = straight
        return {
            relation.key: (
                relation.stated.source or spread[(relation.key, 0)],
                relation.stated.target or spread[(relation.key, 1)],
            )
            for relation in undecided
        }

    def decide(self, undecided: Sequence[Undecided]) -> dict[str, Route]:
        """A whole route for each of *undecided*, by key. One with no way round is left without bends."""
        loops = [relation for relation in undecided if relation.source == relation.target]
        nested = [relation for relation in undecided if self._one_holds_the_other(relation)]
        close = [
            relation for relation in undecided
            if relation.source != relation.target and relation not in nested
            and ends_conflict(self._extents[relation.source], self._extents[relation.target])
        ]
        between = [
            one for one in undecided if one.source != one.target and one not in close and one not in nested
        ]
        ports = self._ports_spread(between, self._sides_chosen(between))
        decided = {
            relation.key: replace(_around_itself(self._extents[relation.source]), label=relation.stated.label)
            for relation in loops
        }
        for relation in nested:
            decided[relation.key] = self._from_whole_to_part(relation)
        # Two elements closer than a stub: no route keeps I1, so the most direct one is drawn.
        for relation in close:
            decided[relation.key] = formed_afresh(
                Route(label=relation.stated.label), self._extents[relation.source], self._extents[relation.target]
            )
        for relation in sorted(between, key=lambda one: one.key):
            leaving, arriving = ports[relation.key]
            route = Route(leaving, arriving, label=relation.stated.label)
            decided[relation.key] = next(
                (
                    found for leniency in Leniency
                    if (found := self.rerouted(route, relation.source, relation.target, relation.decorated, leniency))
                    or (found := self._another_way(relation, leniency))
                ),
                route,
            )
        return self._spread_again(decided, {relation.key: relation for relation in between})

    def _spread_again(self, decided: dict[str, Route], by_key: Mapping[str, Undecided]) -> dict[str, Route]:
        """Ends that came to share a side spread along it again, so no two arrive at one point.

        A relation that found its way only from other sides took the middle of them. A route that
        finds no way from its new port keeps the one it has.
        """
        ends: dict[tuple[str, int], EndOnSide] = {}
        for key, relation in by_key.items():
            stated = (relation.stated.source, relation.stated.target)
            ports = (decided[key].source, decided[key].target)
            for which, ((here, there), port) in enumerate(zip(_both_ways(relation), ports, strict=True)):
                if port is not None and stated[which] is None:
                    ends[(key, which)] = (here, port.side, there)
        sharing: dict[tuple[str, Side], int] = defaultdict(int)
        for here, side, _there in ends.values():
            sharing[(here, side)] += 1
        # An end with its side to itself keeps its port: it may be lined up with the other end.
        spread = {
            end: port for end, port in self._spread(ends).items() if sharing[ends[end][:2]] > 1
        }
        for key, relation in sorted(by_key.items()):
            route = decided[key]
            moved = replace(
                route, source=spread.get((key, 0), route.source), target=spread.get((key, 1), route.target), via=()
            )
            if (moved.source, moved.target) == (route.source, route.target):
                continue
            bunched = course_of(route, self._extents[relation.source], self._extents[relation.target])
            if bunched is not None:
                self._router.forget(bunched)
            again = self.rerouted(moved, relation.source, relation.target, relation.decorated, Leniency.STRICT)
            if again is not None:
                decided[key] = again
            elif bunched is not None:
                self._router.keep_apart_from(bunched)
        return decided

    def _one_holds_the_other(self, relation: Undecided) -> bool:
        source, target = self._extents[relation.source], self._extents[relation.target]
        return relation.source != relation.target and (source.encloses(target) or target.encloses(source))

    def _from_whole_to_part(self, relation: Undecided) -> Route:
        """A relation between a box and an element drawn inside it: one straight run from the part's side
        to the whole's border nearest it, through nothing — the picture draws the whole's own end at its
        edge, where the notation means the whole."""
        source, target = self._extents[relation.source], self._extents[relation.target]
        whole_is_source = source.encloses(target)
        whole, part = (source, target) if whole_is_source else (target, source)
        gaps = {
            Side.TOP: part.top - whole.top, Side.BOTTOM: whole.bottom - part.bottom,
            Side.LEFT: part.left - whole.left, Side.RIGHT: whole.right - part.right,
        }
        for side in sorted(gaps, key=lambda one: gaps[one]):
            at = 0.5
            along = part.left + at * part.width if not leaves_level(side) else part.top + at * part.height
            whole_at = fraction(share_along(whole, along, level=leaves_level(side)))
            part_port, whole_port = Port(side, at), Port(side, whole_at)
            route = Route(whole_port, part_port) if whole_is_source else Route(part_port, whole_port)
            course = course_of(route, source, target)
            if course is not None and self._router.is_clear(
                course, (source, target), _passable(self._extents, self._obstacles, (relation.source, relation.target)),
                (False, False),
            ):
                self._router.keep_apart_from(course)
                return replace(route, label=relation.stated.label)
        return formed_afresh(Route(label=relation.stated.label), source, target)

    def _another_way(self, relation: Undecided, leniency: Leniency = Leniency.STRICT) -> Route | None:
        """A route from other sides, for a relation whose chosen ports have no way between them."""
        for leaving in ([relation.stated.source.side] if relation.stated.source else list(Side)):
            for arriving in ([relation.stated.target.side] if relation.stated.target else list(Side)):
                route = Route(
                    relation.stated.source or self._off_the_band(relation.source, Port(leaving, 0.5)),
                    relation.stated.target or self._off_the_band(relation.target, Port(arriving, 0.5)),
                    label=relation.stated.label,
                )
                found = self.rerouted(route, relation.source, relation.target, relation.decorated, leniency)
                if found is not None:
                    return found
        return None

    def rerouted(
        self, route: Route, source_key: str, target_key: str, decorated: tuple[bool, bool] = (True, True),
        leniency: Leniency = Leniency.SHORT_RUNS,
    ) -> Route | None:
        """*route* with its bends found again around every element, its ports kept; None where there is no way."""
        if route.source is None or route.target is None:
            return None
        found = self._router.route(
            self._extents[source_key], route.source, self._extents[target_key], route.target,
            passable=_passable(self._extents, self._obstacles, (source_key, target_key)), decorated=decorated,
            leniency=leniency, walls=_walls(self._extents, self._obstacles, (source_key, target_key)),
        )
        if found is None:
            return None
        self._router.keep_apart_from(found.course)
        return replace(route, via=_as_bends(found))
