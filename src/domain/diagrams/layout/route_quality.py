"""What makes a route readable, beyond staying attached: rules a router keeps and a picture is checked for.

I1–I5 (`attachment`) say a route belongs to its two elements. These say a reader can follow it, in
two tiers, stated once as data in `RULE_TIERS` and read by both languages through the shared fixtures:

**Hard** — the router keeps them; a laid-out picture that breaks one is reported (W380–W382, W385, W386):

* *text* — no line runs through text (`text_clearance`);
* *A, a straight run into each decorated end* — where a route bends at all, its first and last
  segments are at least `END_RUN` long where a decoration is drawn: the decoration and a clear run
  behind it;
* *C, no shared runs* — no segment runs along another relation's segment, or along the border of an
  element or a box, closer than `LINE_CLEARANCE`. Lines cross at right angles; they never merge;
* *its box* — a relation between two members of a box stays inside the smallest box holding both
  (W385; the router's bounds, `routing.visibility.Bounds`);
* *orthogonal* — every run is upright or level, as drawn and as read back (W386).

A line that keeps these three can be traced from one end to the other.

**Soft** — the router avoids them at a cost and gives one up only where the hard rules leave no other
way; a picture is not reported for them, only counted beside its findings:

* *B, a jog* — a segment between two bends shorter than `SHORTEST_SEGMENT`, or a run that turns back
  along an axis a second time: left, then right, then left again, however long each run. A route
  that goes round something turns back once; one that weaves turns back twice;
* *heads together* — two decorations drawn at one point, or over each other;
* *a label obscured* — a relation's label under a shape or another label.

A course here is a route's orthogonal course, from the border of one element to the border of the
other. Mirrored in `tools/gui/src/domain/layout/routeQuality.ts` from the shared fixtures.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum

from src.domain.diagrams.layout.geometry import Extent, Point

#: How long a route runs straight into an end where it bends at all: the longest decoration this
#: notation draws at an end (a hollow triangle, 18 px) and a clear run behind it.
END_RUN = 30.0

#: The shortest segment between two bends.
SHORTEST_SEGMENT = 16.0

#: How close two parallel runs may come, or a run and a border, before they read as one line.
LINE_CLEARANCE = 6.0

#: How much two runs must share along their length to count as running along each other.
_SHARED_LENGTH = 1.0

#: How far off upright or level a segment may be and still be one.
_SQUARE = 0.5


class Unreadable(StrEnum):
    """What a route does that keeps a reader from following it."""

    BEND_AT_SOURCE = "A:source"
    BEND_AT_TARGET = "A:target"
    KINK = "B"
    RUNS_ALONG = "C"


class Tier(StrEnum):
    HARD = "hard"
    SOFT = "soft"


#: Every readability rule by name, and its tier. The one statement of which rules a router may give up.
RULE_TIERS: Mapping[str, Tier] = {
    "text": Tier.HARD,
    "bend-at-an-end": Tier.HARD,
    "runs-along": Tier.HARD,
    "leaves-common-box": Tier.HARD,
    "orthogonal": Tier.HARD,
    "jog": Tier.SOFT,
    "heads-together": Tier.SOFT,
    "label-obscured": Tier.SOFT,
}


def _length(start: Point, end: Point) -> float:
    return start.distance_to(end)


def bends_at_ends(course: Sequence[Point], decorated: tuple[bool, bool] = (True, True)) -> tuple[Unreadable, ...]:
    """A: the decorated ends of *course* whose straight run is shorter than `END_RUN`, where it bends at all.

    *decorated* says which ends carry a decoration. An end without one needs only the stub I1 asks for.
    """
    if len(course) <= 2:  # noqa: PLR2004 — a straight line has no bend to sit anywhere
        return ()
    return tuple(
        breach
        for breach, run, marked in ((Unreadable.BEND_AT_SOURCE, (course[0], course[1]), decorated[0]),
                                    (Unreadable.BEND_AT_TARGET, (course[-1], course[-2]), decorated[1]))
        if marked and _length(*run) < END_RUN - _SQUARE
    )


def _weaving(course: Sequence[Point]) -> set[int]:
    """The index of each run that turns back along its axis a second time or more."""
    found: set[int] = set()
    for level in (True, False):
        heading, turned = 0, 0
        for index in range(len(course) - 1):
            a, b = course[index], course[index + 1]
            step = (b.x - a.x) if level else (b.y - a.y)
            if abs(step) <= _SQUARE:
                continue
            way = 1 if step > 0 else -1
            if heading and way != heading:
                turned += 1
                if turned >= 2:  # noqa: PLR2004 — once is going round something; twice is weaving
                    found.add(index)
            heading = way
    return found


def kinks(course: Sequence[Point]) -> tuple[int, ...]:
    """B: the index of each segment between two bends shorter than `SHORTEST_SEGMENT`, and of each run
    that turns back along its axis a second time."""
    short = {
        index for index in range(1, len(course) - 2)
        if _length(course[index], course[index + 1]) < SHORTEST_SEGMENT
    }
    return tuple(sorted(short | _weaving(course)))


def _span(start: Point, end: Point) -> tuple[bool, float, float, float] | None:
    """A segment as (level, where it lies across, low, high), or None for a slanted or empty one."""
    if abs(start.y - end.y) <= _SQUARE and abs(start.x - end.x) > _SQUARE:
        return True, start.y, min(start.x, end.x), max(start.x, end.x)
    if abs(start.x - end.x) <= _SQUARE and abs(start.y - end.y) > _SQUARE:
        return False, start.x, min(start.y, end.y), max(start.y, end.y)
    return None


def _edges(extent: Extent) -> tuple[tuple[bool, float, float, float], ...]:
    return (
        (True, extent.top, extent.left, extent.right), (True, extent.bottom, extent.left, extent.right),
        (False, extent.left, extent.top, extent.bottom), (False, extent.right, extent.top, extent.bottom),
    )


def _alongside(run: tuple[bool, float, float, float], other: tuple[bool, float, float, float]) -> bool:
    level, at, low, high = run
    other_level, other_at, other_low, other_high = other
    return (
        level == other_level
        and abs(at - other_at) < LINE_CLEARANCE
        and min(high, other_high) - max(low, other_low) > _SHARED_LENGTH
    )


def runs_along(
    course: Sequence[Point], others: Sequence[Sequence[Point]] = (), borders: Sequence[Extent] = ()
) -> tuple[int, ...]:
    """C: the index of each segment of *course* running along another course's segment, or a border.

    A route's first and last segments end on a border at a right angle and do not run along it; a
    segment that does lies parallel to it.
    """
    lines = [
        span for other in others for start, end in zip(other, other[1:], strict=False)
        if (span := _span(start, end)) is not None
    ] + [edge for border in borders for edge in _edges(border)]
    return tuple(
        index for index in range(len(course) - 1)
        if (run := _span(course[index], course[index + 1])) is not None
        and any(_alongside(run, line) for line in lines)
    )


def unreadable(
    course: Sequence[Point], others: Sequence[Sequence[Point]] = (), borders: Sequence[Extent] = (),
    decorated: tuple[bool, bool] = (True, True),
) -> tuple[Unreadable, ...]:
    """Every rule of A–C *course* breaks, once each."""
    return (
        *bends_at_ends(course, decorated),
        *((Unreadable.KINK,) if kinks(course) else ()),
        *((Unreadable.RUNS_ALONG,) if runs_along(course, others, borders) else ()),
    )


def square_course(through: Sequence[Point]) -> tuple[Point, ...]:
    """The orthogonal course a drawn line with rounded bends follows: each rounding taken back to its corner.

    A rounded bend is drawn as a short slanted chord between the end of one run and the start of the
    next; the corner is where the two runs would meet. A line with no rounding is returned as drawn.
    """
    if len(through) <= 2:  # noqa: PLR2004 — nothing to round
        return tuple(through)
    corners = [through[0]]
    for index in range(1, len(through) - 1):
        before, here, after = through[index - 1], through[index], through[index + 1]
        if _span(before, here) is not None and _span(here, after) is None:
            upright_in = abs(before.x - here.x) <= _SQUARE
            corners.append(Point(here.x, after.y) if upright_in else Point(after.x, here.y))
        elif _span(before, here) is not None and _span(here, after) is not None:
            corners.append(here)
    corners.append(through[-1])
    return tuple(corners)
