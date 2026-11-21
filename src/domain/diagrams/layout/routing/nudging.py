"""Nudging (GD 2009 §5): runs that share a line are pulled apart, and none stays along a box border.

Routes are found independently, so two of them may run along one grid line. Per axis — level runs
first, then upright ones — every run is a **member** of the line it lies on: a run between two bends
may move across its line, within its free space; a stub, a box border and a line drawn already may
not. Members closer than `IDEAL_SEPARATION` that share a stretch form a cluster; a cluster is ordered
so runs that turn the same way keep together and do not cross where they part, then placed
`IDEAL_SEPARATION` apart round where they were, never closer than `LINE_CLEARANCE`, inside each run's
free space. Where a cluster does not fit, it is left as found and its pairs are reported.

A run's free space is what it can sweep without its stretch entering an obstacle, without turning
either neighbouring run round, and — for the run next to a stub — only outward, so the stub only
lengthens.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.orthogonal import half_up
from src.domain.diagrams.layout.route_quality import LINE_CLEARANCE
from src.domain.diagrams.layout.routing.scene import IDEAL_SEPARATION

#: How much two runs must share along their stretch to need separating.
_SHARED = 1.0

#: How many passes the placement makes before it gives up on a cluster.
_PASSES = 50

_UNBOUNDED = 1.0e9

#: How many times an axis is gone over, at most, for runs a placement brought near another cluster.
_ROUNDS = 4

#: How many times both axes are gone over in turn.
_SWEEPS = 2

#: How far off an unbounded side of a run's free space is taken to be, when runs are ordered by it.
_FAR = 500.0


@dataclass
class _Member:
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


def _runs_level(a: Point, b: Point) -> bool:
    return a.y == b.y and a.x != b.x


def _across(point: Point, level: bool) -> float:
    return point.y if level else point.x


def _along(point: Point, level: bool) -> float:
    return point.x if level else point.y


def _free_space(
    course: Sequence[Point], index: int, level: bool, obstacles: Sequence[Extent], outward: Sequence[int],
) -> tuple[float, float]:
    """How far across its line run *index* of *course* may move: between its neighbours' far ends and
    the obstacles its stretch would sweep, and only outward where a neighbour is a stub."""
    a, b = course[index], course[index + 1]
    at, low, high = _across(a, level), min(_along(a, level), _along(b, level)), max(_along(a, level), _along(b, level))
    least, most = -_UNBOUNDED, _UNBOUNDED
    for neighbour in (course[index - 1], course[index + 2]):
        far = _across(neighbour, level)
        least, most = (max(least, far + 1.0), most) if far < at else (least, min(most, far - 1.0))
    for rect in obstacles:
        r_low, r_high = (rect.left, rect.right) if level else (rect.top, rect.bottom)
        r_near, r_far = (rect.top, rect.bottom) if level else (rect.left, rect.right)
        if max(r_low, low) < min(r_high, high):
            if r_far <= at:
                least = max(least, r_far)
            elif r_near >= at:
                most = min(most, r_near)
    for sign in outward:
        least, most = (least, min(most, at)) if sign < 0 else (max(least, at), most)
    return least, most


def _turns(course: Sequence[Point], index: int, level: bool) -> int:
    at = _across(course[index], level)
    total = 0
    for neighbour in (course[index - 1], course[index + 2]):
        far = _across(neighbour, level)
        total += -1 if far < at else 1 if far > at else 0
    return total


def _members(
    courses: Mapping[str, list[Point]], level: bool, movable: frozenset[str] | None,
    obstacles: Mapping[str, Sequence[Extent]], fixed: Sequence[tuple[float, float, float]],
) -> list[_Member]:
    members = [_Member(at, low, high, at, at, 0, "", -1) for at, low, high in fixed]
    for key in sorted(courses):
        course = courses[key]
        last = len(course) - 2
        for index in range(last + 1):
            a, b = course[index], course[index + 1]
            if _runs_level(a, b) != level or (not level and a.x != b.x):
                continue
            at = _across(a, level)
            low, high = sorted((_along(a, level), _along(b, level)))
            if index in (0, last) or (movable is not None and key not in movable):
                members.append(_Member(at, low, high, at, at, 0, key, index))
                continue
            # The run next to a stub may only move outward: away from the port, lengthening the stub.
            outward: list[int] = []
            if index == 1:
                outward.append(1 if _across(course[1], level) > _across(course[0], level) else -1)
            if index == last - 1:
                outward.append(1 if _across(course[last], level) > _across(course[last + 1], level) else -1)
            least, most = _free_space(course, index, level, obstacles[key], outward)
            members.append(_Member(at, low, high, least, most, _turns(course, index, level), key, index))
    return members


def _clusters(members: list[_Member]) -> list[list[_Member]]:
    parent = list(range(len(members)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    order = sorted(range(len(members)), key=lambda index: (members[index].at, index))
    for position, first in enumerate(order):
        for second in order[position + 1 :]:
            if members[second].at - members[first].at >= IDEAL_SEPARATION:
                break
            one, other = members[first], members[second]
            if min(one.high, other.high) - max(one.low, other.low) > _SHARED:
                parent[root(second)] = root(first)
    groups: dict[int, list[_Member]] = {}
    for index in order:
        groups.setdefault(root(index), []).append(members[index])
    return [group for group in groups.values() if len(group) > 1]


def _placed(ordered: list[_Member], separation: float) -> list[float] | None:
    movable = [member for member in ordered if member.movable]
    total = 0.0
    for member in movable:  # added in order, as the browser adds: `sum` compensates, and would differ
        total += member.at
    centre = total / len(movable)
    rank = {id(member): position for position, member in enumerate(movable)}
    places = [
        centre + (rank[id(member)] - (len(movable) - 1) / 2) * separation if member.movable else member.at
        for member in ordered
    ]
    for _ in range(_PASSES):
        for index, member in enumerate(ordered):
            places[index] = min(max(places[index], member.least), member.most)
        for index in range(1, len(ordered)):
            if places[index] < places[index - 1] + separation:
                if ordered[index].movable:
                    places[index] = places[index - 1] + separation
                elif ordered[index - 1].movable:
                    places[index - 1] = places[index] - separation
        for index in range(len(ordered) - 2, -1, -1):
            if places[index] > places[index + 1] - separation:
                if ordered[index].movable:
                    places[index] = places[index + 1] - separation
                elif ordered[index + 1].movable:
                    places[index + 1] = places[index] + separation
        fits = all(
            member.least <= place <= member.most for member, place in zip(ordered, places, strict=True)
        ) and all(places[index] - places[index - 1] >= separation - 1e-9 for index in range(1, len(ordered)))
        if fits:
            return places
    return None


def _middle(member: _Member) -> float:
    """The middle of where a member may go, an unbounded side taken as a long way off."""
    return (max(member.least, member.at - _FAR) + min(member.most, member.at + _FAR)) / 2


def _first_that_fits(cluster: list[_Member]) -> tuple[list[_Member], list[float] | None]:
    """An order of the cluster and places for it, at the ideal separation if any order allows, else the least.

    Runs that turn the same way keep together first; where that order leaves no room — a run that may
    only move one way, next to its stub — they are ordered by where each has room instead.
    """
    orders = (
        sorted(cluster, key=lambda member: (member.turns, _middle(member), member.owner, member.index)),
        sorted(cluster, key=lambda member: (_middle(member), member.owner, member.index)),
    )
    for separation in (IDEAL_SEPARATION, LINE_CLEARANCE + 1.0):
        for ordered in orders:
            if (places := _placed(ordered, separation)) is not None:
                return ordered, places
    return orders[0], None


def nudged(
    courses: Mapping[str, list[Point]], obstacles: Mapping[str, Sequence[Extent]],
    borders: Sequence[Extent], fixed_lines: Sequence[Sequence[Point]] = (), movable: frozenset[str] | None = None,
) -> tuple[dict[str, list[Point]], list[tuple[str, str]]]:
    """*courses* with their shared runs pulled apart; and the pairs that could not be.

    *obstacles* holds, for each connector, what its runs may not sweep into; *borders* the boxes whose
    edges no run may lie along; *fixed_lines* lines drawn already. With *movable*, only those
    connectors' runs move — the others hold still, as a drag's quick pass wants.
    """
    moved = {key: list(course) for key, course in courses.items()}
    # Moving upright runs lengthens or shortens level ones, and the other way round, so both axes are
    # gone over twice; whatever is still too close afterwards, on either axis, is reported.
    for _sweep in range(_SWEEPS):
        for level in (True, False):
            _separated(moved, level, movable, obstacles, _fixed(borders, fixed_lines, level))
    unseparated = [
        pair
        for level in (True, False)
        for cluster in _clusters(_members(moved, level, movable, obstacles, _fixed(borders, fixed_lines, level)))
        if not _apart(cluster)
        for pair in _pairs(cluster)
    ]
    return moved, unseparated


def _fixed(
    borders: Sequence[Extent], fixed_lines: Sequence[Sequence[Point]], level: bool,
) -> list[tuple[float, float, float]]:
    """The lines no run may move and every run keeps clear of: box borders, and lines drawn already."""
    return [
        (edge, low, high)
        for box in borders
        for edge, low, high in (
            ((box.top, box.left, box.right), (box.bottom, box.left, box.right)) if level
            else ((box.left, box.top, box.bottom), (box.right, box.top, box.bottom))
        )
    ] + [
        (_across(a, level), min(_along(a, level), _along(b, level)), max(_along(a, level), _along(b, level)))
        for line in fixed_lines for a, b in zip(line, line[1:], strict=False)
        if (a.y == b.y if level else a.x == b.x) and a != b
    ]


def _separated(
    moved: dict[str, list[Point]], level: bool, movable: frozenset[str] | None,
    obstacles: Mapping[str, Sequence[Extent]], fixed: Sequence[tuple[float, float, float]],
) -> None:
    """One axis's runs pulled apart in place: gone over again, a few times at most, while anything moves,
    since a run moved in one cluster may come near another's."""
    for _round in range(_ROUNDS):
        changed = False
        for cluster in _clusters(_members(moved, level, movable, obstacles, fixed)):
            if _apart(cluster) or not any(member.movable for member in cluster):
                continue
            ordered, places = _first_that_fits(cluster)
            if places is None:
                continue
            for member, place in zip(ordered, places, strict=True):
                whole = half_up(place)
                if member.movable and member.at != whole:
                    changed = True
                    course = moved[member.owner]
                    for at in (member.index, member.index + 1):
                        course[at] = Point(course[at].x, whole) if level else Point(whole, course[at].y)
        if not changed:
            return


def _pairs(cluster: list[_Member]) -> list[tuple[str, str]]:
    """The connectors whose runs lie closer than the least separation, next to each other across the line.

    A border or a line drawn already is no connector, so a run too close to one names its own connector
    twice.
    """
    ordered = sorted(cluster, key=lambda member: (member.at, member.owner, member.index))
    return [
        (min(first.owner or second.owner, second.owner or first.owner),
         max(first.owner or second.owner, second.owner or first.owner))
        for first, second in zip(ordered, ordered[1:], strict=False)
        if second.at - first.at < LINE_CLEARANCE + 1.0 and (first.owner or second.owner)
        and first.owner != second.owner
    ]


def _apart(cluster: list[_Member]) -> bool:
    """Whether a cluster's members already lie at least the least separation apart, every pair."""
    ats = sorted(member.at for member in cluster)
    return all(second - first >= LINE_CLEARANCE + 1.0 for first, second in zip(ats, ats[1:], strict=False))
