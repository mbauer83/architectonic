"""Nudging (GD 2009 §5): runs that share a line are pulled apart, and none stays along a box border.

Routes are found independently, so two of them may run along one grid line. Per axis — level runs
first, then upright ones — every run is a **member** of the line it lies on: a run between two bends
may move across its line, within its free space; a stub, a box border and a line drawn already may
not. Members closer than `IDEAL_SEPARATION` that share a stretch form a cluster; a cluster is ordered
so runs that turn the same way keep together and do not cross where they part, then each two members
that share a stretch are placed `IDEAL_SEPARATION` apart, never closer than `LINE_CLEARANCE`, inside
each run's free space. Two members of one cluster that share no stretch are not held apart: a cluster
chains along a line, and a border at one end of it says nothing of a run at the other. Where a cluster
does not fit, it is left as found and its pairs are reported.

A run's free space is what it can sweep without its stretch entering an obstacle, without turning
either neighbouring run round, and — for the run next to an end — never so near the port that the
end's run falls short of `END_RUN`, or shorter than it is already. The first and last segments of a
course hold a stub and whatever straight run follows it; the run beside one may shorten it to that.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.orthogonal import half_up
from src.domain.diagrams.layout.route_quality import END_RUN, LINE_CLEARANCE
from src.domain.diagrams.layout.routing.placement import Member, first_that_fits, preferred_places, share
from src.domain.diagrams.layout.routing.scene import IDEAL_SEPARATION

_UNBOUNDED = 1.0e9

#: How many times an axis is gone over, at most, for runs a placement brought near another cluster.
_ROUNDS = 4

#: How near two members sharing a stretch must lie to be placed together: twice the ideal separation,
#: so a run placed apart from one is placed knowing the next, rather than onto it.
_REACH = 2 * IDEAL_SEPARATION

#: How many times both axes are gone over in turn.
_SWEEPS = 2


def _runs_level(a: Point, b: Point) -> bool:
    return a.y == b.y and a.x != b.x


def _across(point: Point, level: bool) -> float:
    return point.y if level else point.x


def _along(point: Point, level: bool) -> float:
    return point.x if level else point.y


def _free_space(
    course: Sequence[Point], index: int, level: bool, obstacles: Sequence[Extent],
    outward: Sequence[tuple[int, float]],
) -> tuple[float, float]:
    """How far across its line run *index* of *course* may move: between its neighbours' far ends and
    the obstacles its stretch would sweep, and no nearer a port than *outward* allows: for each end
    beside it, which way is away from the port and the nearest it may come."""
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
    for sign, nearest in outward:
        least, most = (least, min(most, nearest)) if sign < 0 else (max(least, nearest), most)
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
) -> list[Member]:
    members = [Member(at, low, high, at, at, 0, "", -1) for at, low, high in fixed]
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
                members.append(Member(at, low, high, at, at, 0, key, index))
                continue
            # The run next to an end keeps the end's run at least END_RUN long, or as long as it is.
            outward: list[tuple[int, float]] = []
            for next_to_end, port, beside in ((index == 1, course[0], course[1]),
                                              (index == last - 1, course[last + 1], course[last])):
                if next_to_end:
                    sign = 1 if _across(beside, level) > _across(port, level) else -1
                    reach = _across(port, level) + sign * END_RUN
                    outward.append((sign, min(at, reach) if sign > 0 else max(at, reach)))
            least, most = _free_space(course, index, level, obstacles[key], outward)
            members.append(Member(at, low, high, least, most, _turns(course, index, level), key, index))
    return _clear_of_the_fixed(members)


def _clear_of_the_fixed(members: list[Member]) -> list[Member]:
    """Each run's free space kept the least separation clear of every box border and line drawn already
    across its stretch: a run placed onto one, by a cluster that did not hold it, would only be moved
    back by the next."""
    fixed = [member for member in members if not member.owner]
    for member in members:
        if not member.movable:
            continue
        for line in fixed:
            if share(member, line):
                if line.at > member.at:
                    member.most = min(member.most, line.at - (LINE_CLEARANCE + 1.0))
                elif line.at < member.at:
                    member.least = max(member.least, line.at + (LINE_CLEARANCE + 1.0))
        if member.least > member.most:
            member.least = member.most = member.at
    return members


def _clusters(members: list[Member]) -> list[list[Member]]:
    parent = list(range(len(members)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    order = sorted(range(len(members)), key=lambda index: (members[index].at, index))
    for position, first in enumerate(order):
        for second in order[position + 1 :]:
            if members[second].at - members[first].at >= _REACH:
                break
            one, other = members[first], members[second]
            if share(one, other):
                parent[root(second)] = root(first)
    groups: dict[int, list[Member]] = {}
    for index in order:
        groups.setdefault(root(index), []).append(members[index])
    return [group for group in groups.values() if len(group) > 1]


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
    fixed = {axis: _fixed(borders, fixed_lines, axis) for axis in (True, False)}

    def conflicts(candidate: dict[str, list[Point]]) -> list[tuple[str, str]]:
        return [pair for axis, lines in fixed.items()
                for cluster in _clusters(_members(candidate, axis, movable, obstacles, lines))
                if not _apart(cluster) for pair in _pairs(cluster)]

    for _sweep in range(_SWEEPS):
        for axis, lines in fixed.items():
            _separated(moved, axis, movable, obstacles, lines)
    unseparated = conflicts(moved)
    if unseparated or movable is not None:
        return moved, unseparated

    # Preserve the feasible drawing until the two axes of the wider drawing agree.
    wider = {key: list(course) for key, course in moved.items()}
    for axis, lines in fixed.items():
        _separated(wider, axis, movable, obstacles, lines, widen=True)
    return (moved if wider != moved and conflicts(wider) else wider), []


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
    obstacles: Mapping[str, Sequence[Extent]], fixed: Sequence[tuple[float, float, float]], *, widen: bool = False,
) -> None:
    """One axis's runs pulled apart in place: gone over again, a few times at most, while anything moves,
    since a run moved in one cluster may come near another's."""
    for _round in range(1 if widen else _ROUNDS):
        changed = False
        for cluster in _clusters(_members(moved, level, movable, obstacles, fixed)):
            if _apart(cluster) != widen or not any(member.movable for member in cluster):
                continue
            ordered, places = (cluster, preferred_places(cluster)) if widen else first_that_fits(cluster)
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


def _pairs(cluster: list[Member]) -> list[tuple[str, str]]:
    """The connectors whose runs share a stretch closer than the least separation.

    A border or a line drawn already is no connector, so a run too close to one names its own connector
    twice.
    """
    ordered = sorted(cluster, key=lambda member: (member.at, member.owner, member.index))
    return [
        (min(first.owner or second.owner, second.owner or first.owner),
         max(first.owner or second.owner, second.owner or first.owner))
        for position, first in enumerate(ordered) for second in ordered[position + 1 :]
        if second.at - first.at < LINE_CLEARANCE + 1.0 and share(first, second)
        and (first.owner or second.owner) and first.owner != second.owner
    ]


def _apart(cluster: list[Member]) -> bool:
    """Whether each two members of a cluster that share a stretch lie at least the least separation apart."""
    return all(
        abs(second.at - first.at) >= LINE_CLEARANCE + 1.0
        for position, first in enumerate(cluster) for second in cluster[position + 1 :]
        if share(first, second)
    )
