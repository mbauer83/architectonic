"""Decides what a layout leaves to the router: which sides a relation attaches on, where along them, and its bends.

Three steps, each over every undecided relation at once, because each depends on the others' answers:

1. **Sides** — the pair that looks cheapest, counting how crowded each side already is. Only the
   pairs that face the other end are compared, and by an estimate rather than a trial route: on a
   view of a few hundred elements sixteen searched trials per relation are the whole budget.
2. **Ports** — the ends sharing one side of one element are spread along it, in the order of what
   they lead to, so they do not cross on the way out.
3. **Bends** — each relation routed around every element, keeping apart from those already routed.

A port the layout states is kept; so is everything about a relation whose two ports are stated.
`rerouted` is the third step alone, for the arrow a move made cross an element (I5): its sides and
ports stay, and only its bends are found again.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from src.domain.diagrams.layout.attachment import fraction, share_along
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Route, Side
from src.domain.diagrams.layout.orthogonal import STUB, half_up, leaves_level
from src.infrastructure.rendering.layout.router import Routed, Router

#: What attaching on a side another relation already uses costs when sides are chosen.
_CROWDED = 90.0


@dataclass(frozen=True)
class Undecided:
    """One relation the router decides: its key, its two ends, and whatever the layout does state."""

    key: str
    source: str
    target: str
    stated: Route = Route()


def _facing_sides(extent: Extent, other: Extent) -> list[Side]:
    """The sides of *extent* that look towards *other*, the one across the wider gap first."""
    across = Side.RIGHT if other.centre.x > extent.centre.x else Side.LEFT
    down = Side.BOTTOM if other.centre.y > extent.centre.y else Side.TOP
    gap_x = max(other.left - extent.right, extent.left - other.right)
    gap_y = max(other.top - extent.bottom, extent.top - other.bottom)
    return [across, down] if gap_x > gap_y else [down, across]


def _passable(extents: Mapping[str, Extent], obstacles: Mapping[str, Extent], ends: tuple[str, str]) -> frozenset[str]:
    """The elements a relation may cross: those one of its ends is drawn inside, and an end that is a box."""
    own = [extents[end] for end in ends if end in extents]
    return frozenset(
        key for key, extent in obstacles.items()
        if key not in ends and any(extent.encloses(end) or end.encloses(extent) for end in own)
    )


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


class RelationRouting:
    """The routing of one arrangement: what is already settled, and what the router is asked to decide."""

    def __init__(self, extents: Mapping[str, Extent], obstacles: Mapping[str, Extent]) -> None:
        """*extents* is everything a relation may end at; *obstacles* the elements none may cross."""
        self._extents = extents
        self._obstacles = obstacles
        self._router = Router(obstacles)

    def keep_apart_from(self, course: Sequence[Point]) -> None:
        self._router.keep_apart_from(course)

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

    def _ports_spread(
        self, undecided: Sequence[Undecided], sides: Mapping[str, tuple[Side, Side]]
    ) -> dict[str, tuple[Port, Port]]:
        """Each undecided end's port: the ends sharing a side spread along it in the order of what they lead to."""
        sharing: dict[tuple[str, Side], list[tuple[float, str, int]]] = defaultdict(list)
        for relation in undecided:
            both_ways = ((relation.source, relation.target), (relation.target, relation.source))
            for which, (here, there) in enumerate(both_ways):
                side, other = sides[relation.key][which], self._extents[there].centre
                sharing[(here, side)].append((other.y if leaves_level(side) else other.x, relation.key, which))
        spread: dict[tuple[str, int], Port] = {}
        alone: set[tuple[str, int]] = set()
        for (_element, side), ends in sharing.items():
            for position, (_along, key, which) in enumerate(sorted(ends), start=1):
                spread[(key, which)] = Port(side, fraction(position / (len(ends) + 1)))
            if len(ends) == 1:
                alone.add((ends[0][1], ends[0][2]))
        # An end with a side to itself has no neighbour to keep clear of: where both ends of a
        # relation do, and the two elements overlap across the gap, the relation runs straight.
        for relation in undecided:
            both_alone = (relation.key, 0) in alone and (relation.key, 1) in alone
            straight = both_alone and _in_line(
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
        between = [relation for relation in undecided if relation.source != relation.target]
        ports = self._ports_spread(between, self._sides_chosen(between))
        decided = {
            relation.key: replace(_around_itself(self._extents[relation.source]), label=relation.stated.label)
            for relation in loops
        }
        for relation in sorted(between, key=lambda one: one.key):
            leaving, arriving = ports[relation.key]
            route = Route(leaving, arriving, label=relation.stated.label)
            decided[relation.key] = (
                self.rerouted(route, relation.source, relation.target) or self._another_way(relation) or route
            )
        return decided

    def _another_way(self, relation: Undecided) -> Route | None:
        """A route from other sides, for a relation whose chosen ports have no way between them."""
        for leaving in ([relation.stated.source.side] if relation.stated.source else list(Side)):
            for arriving in ([relation.stated.target.side] if relation.stated.target else list(Side)):
                route = Route(
                    relation.stated.source or Port(leaving, 0.5), relation.stated.target or Port(arriving, 0.5),
                    label=relation.stated.label,
                )
                if (found := self.rerouted(route, relation.source, relation.target)) is not None:
                    return found
        return None

    def rerouted(self, route: Route, source_key: str, target_key: str) -> Route | None:
        """*route* with its bends found again around every element, its ports kept; None where there is no way."""
        if route.source is None or route.target is None:
            return None
        found = self._router.route(
            self._extents[source_key], route.source, self._extents[target_key], route.target,
            passable=_passable(self._extents, self._obstacles, (source_key, target_key)),
        )
        if found is None:
            return None
        self._router.keep_apart_from(found.course)
        return replace(route, via=_as_bends(found))
