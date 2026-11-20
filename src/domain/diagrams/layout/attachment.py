"""Arrows stay attached: what a route owes the two elements it joins, and how it is kept when one moves.

Five invariants, numbered as the plan numbers them:

* **I1** — each end sits on its element's border and leaves it straight outward by at least one stub.
  A port is a side and a fraction, so an end cannot be *off* its border; what is left to keep is the
  direction and the length of the first run.
* **I2** — no segment passes through the relation's own ends.
* **I3** — when an element moves or is resized, the bend next to each attached end follows the port
  on the axis that keeps that end's segment straight: the arrow extends, contracts and shifts, and
  keeps its shape.
* **I4** — only where following breaks I1 or I2: the end turns to the side its route lies beyond;
  failing that the bend next to it goes; failing that the arrow is formed afresh, facing its ends.
* **I5** — an arrow crosses no other element. Finding out is decided here; going around is the
  router's work, so `keep_attached` names the arrows that need it and changes nothing else.

Two connected elements that overlap or touch are a conflict no route satisfies. That is reported,
never repaired. Mirrored in `tools/gui/src/domain/layout/attachment.ts` from the shared fixtures.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Route, Side
from src.domain.diagrams.layout.orthogonal import (
    IN_LINE,
    OUTWARD,
    STUB,
    course_of,
    half_up,
    leaves_level,
    port_point,
    stated_course,
)

#: How far inside an element a segment must run before it counts as through it.
THROUGH_MARGIN = 2.0

#: How close to a corner a turned end may attach, as a fraction of the side.
_FROM_THE_CORNER = 0.1

#: How many times an end is turned or relieved of a bend before the arrow is formed afresh.
_TRIES_PER_END = 3

_SIDES_IN_ORDER = (Side.TOP, Side.RIGHT, Side.BOTTOM, Side.LEFT)

#: A run has two ends.
_A_RUN = 2


class Breach(StrEnum):
    """What a route fails to keep towards its own two ends."""

    SOURCE_NOT_OUTWARD = "I1:source"
    TARGET_NOT_OUTWARD = "I1:target"
    THROUGH_SOURCE = "I2:source"
    THROUGH_TARGET = "I2:target"


def fraction(value: float) -> float:
    """*value* as a port's fraction is written: within the side, to four places."""
    return half_up(max(0.0, min(1.0, value)) * 10000) / 10000


def leaves_outward(side: Side, start: Point, toward: Point) -> bool:
    """Whether the run from *start* goes along the side's outward normal for at least one stub."""
    out_x, out_y = OUTWARD[side]
    travelled = (toward.x - start.x) * out_x + (toward.y - start.y) * out_y
    strayed = abs((toward.x - start.x) * out_y) + abs((toward.y - start.y) * out_x)
    return travelled >= STUB and strayed <= IN_LINE


def runs_through(course: Sequence[Point], extent: Extent) -> bool:
    """Whether any segment of *course* passes inside *extent*, a margin in from its border."""
    interior = extent.shrunk_by(THROUGH_MARGIN)
    return interior is not None and any(
        interior.is_entered_by(course[index], course[index + 1]) for index in range(len(course) - 1)
    )


def breaches_of(route: Route, source: Extent | None, target: Extent | None) -> tuple[Breach, ...]:
    """Everything *route* fails to keep towards its ends (I1, I2), as far as it and the extents say.

    An end with no stated port is the router's to decide and is not judged for how it leaves; an
    element whose extent is not known is not judged at all. Silence is not evidence.
    """
    course = stated_course(route, source, target)
    if len(course) < _A_RUN:
        return ()
    checks = (
        (Breach.SOURCE_NOT_OUTWARD, route.source is not None and source is not None
            and not leaves_outward(route.source.side, course[0], course[1])),
        (Breach.TARGET_NOT_OUTWARD, route.target is not None and target is not None
            and not leaves_outward(route.target.side, course[-1], course[-2])),
        (Breach.THROUGH_SOURCE, source is not None and runs_through(course, source)),
        (Breach.THROUGH_TARGET, target is not None and runs_through(course, target)),
    )
    return tuple(breach for breach, broken in checks if broken)


def ends_conflict(source: Extent, target: Extent) -> bool:
    """Whether two connected elements overlap or sit closer than a stub: a conflict no route satisfies."""
    return (
        source.left < target.right + STUB and target.left < source.right + STUB
        and source.top < target.bottom + STUB and target.top < source.bottom + STUB
    )


def elements_crossed(
    course: Sequence[Point], extents: Mapping[str, Extent], own_ends: tuple[str, str]
) -> tuple[str, ...]:
    """The elements other than its own ends that *course* passes through (I5).

    An element one of the ends is drawn inside is not another element to it: a part's arrow leaves
    its whole by crossing its border.
    """
    own = [extents[end] for end in own_ends if end in extents]
    return tuple(
        key for key, extent in extents.items()
        if key not in own_ends
        and not any(extent.encloses(end) for end in own)
        and runs_through(course, extent)
    )


def _flipped(route: Route) -> Route:
    return replace(route, source=route.target, target=route.source, via=route.via[::-1])


def _next_after_source(route: Route, target: Extent) -> Point:
    """The point the route makes for on leaving its source: its first bend, else its other end."""
    if route.via:
        return Point(*route.via[0])
    return port_point(target, route.target) if route.target is not None else target.centre


def _first_bend_following(route: Route, source: Extent) -> Route:
    """I3: the first bend moved onto the source port's line, on the axis that keeps that run straight."""
    if not route.via or route.source is None:
        return route
    port, (x, y) = port_point(source, route.source), route.via[0]
    followed = (x, half_up(port.y)) if leaves_level(route.source.side) else (half_up(port.x), y)
    return replace(route, via=(followed, *route.via[1:]))


def _outward_run(route: Route, source: Extent, target: Extent) -> float:
    if route.source is None:
        return STUB
    start, toward = port_point(source, route.source), _next_after_source(route, target)
    out_x, out_y = OUTWARD[route.source.side]
    return (toward.x - start.x) * out_x + (toward.y - start.y) * out_y


def _side_facing(route: Route, source: Extent, target: Extent) -> Port | None:
    """I4: the side of *source* its route lies beyond by at least a stub, or None where it lies beyond none."""
    toward = _next_after_source(route, target)
    clear = {
        Side.TOP: source.top - toward.y, Side.RIGHT: toward.x - source.right,
        Side.BOTTOM: toward.y - source.bottom, Side.LEFT: source.left - toward.x,
    }
    side = max(_SIDES_IN_ORDER, key=lambda candidate: clear[candidate])
    if clear[side] < STUB:
        return None
    along = _share(source, toward.y if leaves_level(side) else toward.x, level=leaves_level(side))
    return Port(side, fraction(max(_FROM_THE_CORNER, min(1 - _FROM_THE_CORNER, along))))


def _share(extent: Extent, coordinate: float, *, level: bool) -> float:
    """How far along a side *coordinate* lies: down a left or right side, across a top or bottom one."""
    length = extent.height if level else extent.width
    return (coordinate - (extent.top if level else extent.left)) / length if length > 0 else 0.5


def _settled_at_source(route: Route, source: Extent, target: Extent) -> Route:
    """The route with its source end following (I3) and, where that is not enough, turned or relieved (I4)."""
    settled = _first_bend_following(route, source)
    for _ in range(_TRIES_PER_END):
        if _outward_run(settled, source, target) >= STUB:
            break
        if (turned := _side_facing(settled, source, target)) is not None:
            settled = _first_bend_following(replace(settled, source=turned), source)
        elif settled.via:
            settled = _first_bend_following(replace(settled, via=settled.via[1:]), source)
        else:
            break
    return settled


def _candidates_facing(source: Extent, target: Extent) -> list[Route]:
    """The ways to join two elements afresh, the most direct first: straight, a Z, an L either way round."""
    gap_x = max(target.left - source.right, source.left - target.right)
    gap_y = max(target.top - source.bottom, source.top - target.bottom)
    rightward, downward = target.centre.x > source.centre.x, target.centre.y > source.centre.y
    across = (Side.RIGHT, Side.LEFT) if rightward else (Side.LEFT, Side.RIGHT)
    down = (Side.BOTTOM, Side.TOP) if downward else (Side.TOP, Side.BOTTOM)
    level = gap_x >= gap_y
    facing = across if level else down
    shared = (
        (max(source.top, target.top), min(source.bottom, target.bottom)) if level
        else (max(source.left, target.left), min(source.right, target.right))
    )
    candidates: list[Route] = []
    if shared[1] > shared[0]:
        middle = (shared[0] + shared[1]) / 2
        candidates.append(Route(
            Port(facing[0], fraction(_share(source, middle, level=level))),
            Port(facing[1], fraction(_share(target, middle, level=level))),
        ))
    return [
        *candidates,
        Route(Port(facing[0], 0.5), Port(facing[1], 0.5)),
        Route(Port(across[0], 0.5), Port(down[1], 0.5)),
        Route(Port(down[0], 0.5), Port(across[1], 0.5)),
    ]


def formed_afresh(route: Route, source: Extent, target: Extent) -> Route:
    """A route facing its two ends, keeping only where *route*'s label sits: the first way that breaks nothing."""
    candidates = _candidates_facing(source, target)
    chosen = next((made for made in candidates if not breaches_of(made, source, target)), candidates[0])
    return replace(chosen, label=route.label)


def reattached(route: Route, source: Extent, target: Extent) -> Route:
    """*route* as it runs once its ends are where *source* and *target* now are (I3, then I4)."""
    if route.source is None or route.target is None:
        return route
    from_source = _settled_at_source(route, source, target)
    settled = _flipped(_settled_at_source(_flipped(from_source), target, source))
    return formed_afresh(route, source, target) if breaches_of(settled, source, target) else settled


@dataclass(frozen=True)
class Reattachment:
    """What keeping arrows attached came to, for one change to where elements are."""

    #: Every route, by relation key: those of the elements that changed repaired, the rest as they were.
    routes: Mapping[str, Route]
    #: I5 — each repaired relation that now crosses another element, with the elements it crosses.
    crossing: Mapping[str, tuple[str, ...]]
    #: Relations whose two elements overlap or touch, which no route joins.
    conflicts: tuple[str, ...]


def keep_attached(
    routes: Mapping[str, Route],
    *,
    ends: Mapping[str, tuple[str, str]],
    extents: Mapping[str, Extent],
    changed: Collection[str],
) -> Reattachment:
    """Every route kept attached after the elements in *changed* moved or were resized.

    *extents* is where every element sits now. Only relations with an end among *changed* are
    touched — a drop changes only what it has to. A relation whose route leaves a port unstated,
    that joins an element to itself, or one of whose ends has no known extent is left as it is.
    """
    kept = dict(routes)
    crossing: dict[str, tuple[str, ...]] = {}
    conflicts: list[str] = []
    for key, route in routes.items():
        source_key, target_key = ends.get(key, ("", ""))
        if source_key == target_key or not {source_key, target_key} & set(changed):
            continue
        source, target = extents.get(source_key), extents.get(target_key)
        if source is None or target is None or route.source is None or route.target is None:
            continue
        if ends_conflict(source, target):
            conflicts.append(key)
        kept[key] = reattached(route, source, target)
        course = course_of(kept[key], source, target)
        if course is not None and (crossed := elements_crossed(course, extents, (source_key, target_key))):
            crossing[key] = crossed
    return Reattachment(routes=kept, crossing=crossing, conflicts=tuple(conflicts))
