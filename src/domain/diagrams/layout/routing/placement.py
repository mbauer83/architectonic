"""Where nudging places the runs of one cluster: an order, then places each two sharing a stretch apart.

What may not move keeps its place and each run stays on its side of it; between two such, runs that
turn the same way keep together, then they are ordered by where each has room, then as they lie, and
a small cluster is tried in every order. Two members that share no stretch are not held apart. A
cluster no order fits is placed one run at a time, each nearest where it lies clear of those before.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from itertools import permutations

from src.domain.diagrams.layout.route_quality import LINE_CLEARANCE
from src.domain.diagrams.layout.routing.scene import IDEAL_SEPARATION

#: How much two runs must share along their stretch to need separating.
_SHARED = 1.0

#: How many passes the placement makes before it gives up on a cluster.
_PASSES = 50

#: The most members a cluster may have for every order of it to be tried.
_PERMUTED = 6

#: How far off an unbounded side of a run's free space is taken to be, when runs are ordered by it.
_FAR = 500.0


@dataclass
class Member:
    at: float
    low: float
    high: float
    #: The range it may be moved within; equal ends for a member that may not move.
    least: float
    most: float
    #: Which way its route turns at its two ends, summed: -2 both towards smaller, +2 both larger.
    turns: int
    owner: str
    index: int

    @property
    def movable(self) -> bool:
        return self.least < self.most


def share(one: Member, other: Member) -> bool:
    return min(one.high, other.high) - max(one.low, other.low) > _SHARED


def _placed(ordered: list[Member], separation: float) -> list[float] | None:
    """Places for *ordered*, in its order, each two that share a stretch *separation* apart; or None."""
    places = [member.at for member in ordered]
    before = [[earlier for earlier in range(later) if share(ordered[earlier], ordered[later])]
              for later in range(len(ordered))]
    for _ in range(_PASSES):
        for index, member in enumerate(ordered):
            places[index] = min(max(places[index], member.least), member.most)
        for later in range(len(ordered)):
            for earlier in before[later]:
                if places[later] < places[earlier] + separation:
                    if ordered[later].movable:
                        places[later] = places[earlier] + separation
                    elif ordered[earlier].movable:
                        places[earlier] = places[later] - separation
        for later in range(len(ordered) - 1, -1, -1):
            for earlier in reversed(before[later]):
                if places[earlier] > places[later] - separation:
                    if ordered[earlier].movable:
                        places[earlier] = places[later] - separation
                    elif ordered[later].movable:
                        places[later] = places[earlier] + separation
        fits = all(
            member.least <= place <= member.most for member, place in zip(ordered, places, strict=True)
        ) and all(
            places[later] - places[earlier] >= separation - 1e-9
            for later in range(len(ordered)) for earlier in before[later]
        )
        if fits:
            return places
    return None


def _middle(member: Member) -> float:
    """The middle of where a member may go, an unbounded side taken as a long way off."""
    return (max(member.least, member.at - _FAR) + min(member.most, member.at + _FAR)) / 2


def first_that_fits(cluster: list[Member]) -> tuple[list[Member], list[float] | None]:
    """An order of the cluster and places for it, at the ideal separation if any order allows, else the least.

    What may not move keeps its place, and each run stays on its side of it. Between two such, runs that
    turn the same way keep together first; where that order leaves no room — a run that may only move
    one way, next to its stub — they are ordered by where each has room instead, and last as they lie.
    """
    fixed = sorted(member.at for member in cluster if not member.movable)

    def band(member: Member) -> int:
        return bisect_left(fixed, member.at)

    orders = (
        sorted(cluster, key=lambda member: (band(member), member.turns, _middle(member), member.owner, member.index)),
        sorted(cluster, key=lambda member: (band(member), _middle(member), member.owner, member.index)),
        sorted(cluster, key=lambda member: (member.at, member.owner, member.index)),
    )
    # A small cluster none of those orders fits is tried in every order, the first order's first.
    every = list(orders)
    if len(cluster) <= _PERMUTED:
        every += [list(order) for order in permutations(orders[0])]
    for separation in (IDEAL_SEPARATION, LINE_CLEARANCE + 1.0):
        for ordered in every:
            if (places := _placed(ordered, separation)) is not None:
                return ordered, places
    return orders[0], _one_by_one(orders[0])


def _one_by_one(ordered: list[Member]) -> list[float]:
    """Places for a cluster no order fits as a whole: what may not move first, then each run in turn at
    the place nearest where it lies that keeps clear of those placed before it — at the ideal separation
    where it can, the least where it cannot, where it lies where neither. Part of a cluster apart is
    better than none of it."""
    places = {id(member): member.at for member in ordered}
    placed = [member for member in ordered if not member.movable]
    for member in ordered:
        if not member.movable:
            continue
        sharing = [other for other in placed if share(member, other)]
        for separation in (IDEAL_SEPARATION, LINE_CLEARANCE + 1.0):
            candidates = [member.at] + [
                places[id(other)] + sign * separation for other in sharing for sign in (-1, 1)
            ]
            clear = [
                place for place in candidates
                if member.least <= place <= member.most
                and all(abs(place - places[id(other)]) >= separation - 1e-9 for other in sharing)
            ]
            if clear:
                places[id(member)] = min(clear, key=lambda place: (abs(place - member.at), place))
                break
        placed.append(member)
    return [places[id(member)] for member in ordered]
