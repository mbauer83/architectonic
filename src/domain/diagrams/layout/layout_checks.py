"""What a stated layout gets wrong, decided from the block and the extents of what it places.

Two questions, kept apart because they need different things:

* **Does every entry name something?** A layout is keyed by the identities the diagram uses, so an
  entry for an instance, grouping or relation the diagram does not hold is geometry for nothing.
  `entries_naming_nothing` answers from the block and the diagram's identities alone.
* **Is the geometry sound?** `check_layout_geometry` answers over extents, for the four things no
  route or stacking repairs: an end that does not leave its element outward (I1), a route through
  one of its own ends (I2), two connected elements over each other, and a box over an element that
  is not inside it.

A port is a side and a fraction along it, so an end *off* its element's border cannot be stated at
all; what I1 leaves to check is the direction the relation leaves in. An element whose extent is not
known — it is placed but not sized, and nobody supplied what the renderer drew — is passed over:
silence is not evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from src.domain.diagrams.authored_groupings import RuleKey, is_rule_key, read_rule_key
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Layout, Placed, Port, Route, Side
from src.domain.diagrams.layout.picture_checks import are_drawn_over_each_other

#: How far a relation runs straight out of its element before it may turn: the router's margin.
STUB = 12.0

#: How far inside an end a segment must run before it counts as through it.
_THROUGH_MARGIN = 2.0

#: How far off the outward normal a first segment may sit and still count as perpendicular.
_STRAIGHT_TOLERANCE = 0.5

_OUTWARD: Mapping[Side, tuple[int, int]] = {
    Side.TOP: (0, -1), Side.RIGHT: (1, 0), Side.BOTTOM: (0, 1), Side.LEFT: (-1, 0),
}


@dataclass(frozen=True)
class DiagramIdentities:
    """What a diagram holds that a layout may name."""

    instances: frozenset[str]
    grouping_ids: frozenset[str]
    #: Every relation the diagram draws, by key text, with the instances at its ends.
    relations: Mapping[str, tuple[str, str]]
    #: Whether any element of the diagram satisfies a rule path — a rule nothing satisfies draws no box.
    rule_admits: Callable[[RuleKey], bool]


@dataclass(frozen=True)
class EntriesNamingNothing:
    """The layout's keys that name nothing on the diagram, by the section each sits in."""

    elements: tuple[str, ...] = ()
    boxes: tuple[str, ...] = ()
    #: Rule keys no element satisfies. Apart from *boxes*: a rule empties when the model moves, not
    #: only when somebody edits the diagram.
    rules: tuple[str, ...] = ()
    relations: tuple[str, ...] = ()
    stacked: tuple[str, ...] = ()

    def any(self) -> bool:
        return bool(self.elements or self.boxes or self.rules or self.relations or self.stacked)


def entries_naming_nothing(layout: Layout, known: DiagramIdentities) -> EntriesNamingNothing:
    """Every key of *layout* that names nothing *known*."""
    def unsatisfied(key: str) -> bool:
        return is_rule_key(key) and not known.rule_admits(read_rule_key(key))

    return EntriesNamingNothing(
        elements=tuple(key for key in layout.elements if key not in known.instances),
        boxes=tuple(key for key in layout.boxes if not is_rule_key(key) and key not in known.grouping_ids),
        rules=tuple(dict.fromkeys(key for key in (*layout.boxes, *layout.z) if unsatisfied(key))),
        relations=tuple(key for key in layout.relations if key not in known.relations),
        stacked=tuple(
            key for key in layout.z
            if not is_rule_key(key) and key not in known.instances and key not in known.grouping_ids
        ),
    )


def pruned_to(layout: Layout, known: DiagramIdentities) -> tuple[Layout, EntriesNamingNothing]:
    """*layout* without the entries naming an instance, grouping or relation the diagram no longer holds.

    A rule key is kept: whether a rule still has members is the model's to say, and it may again.
    """
    dangling = entries_naming_nothing(layout, known)
    kept = layout.without(
        elements=frozenset((*dangling.elements, *dangling.stacked)),
        boxes=frozenset((*dangling.boxes, *dangling.stacked)),
        relations=frozenset(dangling.relations),
    )
    return kept, dangling


class LayoutDefect(StrEnum):
    """The four things a stated layout's geometry decides, in a reviewer's words."""

    END_NOT_LEAVING_OUTWARD = "a relation that does not leave its element straight outward"
    ROUTE_THROUGH_OWN_END = "a relation routed through one of its own ends"
    CONNECTED_ELEMENTS_OVERLAP = "two connected elements over each other"
    BOX_HIDES_ELEMENT = "a box over an element that is not inside it"


@dataclass(frozen=True)
class LayoutFinding:
    """One place the layout is decidably wrong, by the layout keys of what it concerns.

    For the two route defects: the relation, then the end concerned. For an overlap: the relation
    and its two ends. For a hidden element: the box, then the element.
    """

    defect: LayoutDefect
    subjects: tuple[str, ...]


def placed_extent(placed: Placed, drawn_size: tuple[float, float] | None = None) -> Extent | None:
    """The rectangle *placed* occupies: its stated size, else the size it was *drawn* at, else unknown."""
    size = (placed.w, placed.h) if placed.w is not None and placed.h is not None else drawn_size
    if size is None:
        return None
    return Extent(placed.x, placed.y, placed.x + size[0], placed.y + size[1])


def port_point(extent: Extent, port: Port) -> Point:
    """Where *port* lies on *extent*'s border: along a side from its top or its left."""
    along_x = extent.left + port.at * extent.width
    along_y = extent.top + port.at * extent.height
    return {
        Side.TOP: Point(along_x, extent.top),
        Side.BOTTOM: Point(along_x, extent.bottom),
        Side.LEFT: Point(extent.left, along_y),
        Side.RIGHT: Point(extent.right, along_y),
    }[port.side]


def _leaves_outward(port: Port, start: Point, toward: Point) -> bool:
    """Whether the segment from *start* runs along the side's outward normal for at least one stub."""
    out_x, out_y = _OUTWARD[port.side]
    travelled = (toward.x - start.x) * out_x + (toward.y - start.y) * out_y
    strayed = abs((toward.x - start.x) * out_y) + abs((toward.y - start.y) * out_x)
    return travelled >= STUB and strayed <= _STRAIGHT_TOLERANCE


def _course(route: Route, source: Extent | None, target: Extent | None) -> list[Point]:
    """The points the route is stated to run through; an end with no port or no extent is left out."""
    start = [port_point(source, route.source)] if source is not None and route.source is not None else []
    end = [port_point(target, route.target)] if target is not None and route.target is not None else []
    return [*start, *(Point(x, y) for x, y in route.via), *end]


def _runs_through(course: Sequence[Point], extent: Extent) -> bool:
    interior = extent.shrunk_by(_THROUGH_MARGIN)
    return interior is not None and any(
        interior.is_entered_by(course[index], course[index + 1]) for index in range(len(course) - 1)
    )


def _route_findings(
    key: str, route: Route, ends: tuple[str, str], extents: Mapping[str, Extent]
) -> list[LayoutFinding]:
    source, target = extents.get(ends[0]), extents.get(ends[1])
    course = _course(route, source, target)
    findings: list[LayoutFinding] = []
    leaving = (
        (ends[0], route.source, source, course[:2]),
        (ends[1], route.target, target, course[-1:-3:-1]),
    )
    for end, port, extent, first_segment in leaving:
        if port is not None and extent is not None and len(first_segment) == 2 and not _leaves_outward(
            port, first_segment[0], first_segment[1]
        ):
            findings.append(LayoutFinding(LayoutDefect.END_NOT_LEAVING_OUTWARD, (key, end)))
    findings.extend(
        LayoutFinding(LayoutDefect.ROUTE_THROUGH_OWN_END, (key, end))
        for end, extent in zip(ends, (source, target), strict=True)
        if extent is not None and _runs_through(course, extent)
    )
    return findings


def _overlap_as_a_conflict(first: Extent, second: Extent) -> bool:
    """Drawn over each other with neither inside the other: an element holding its part is not a conflict."""
    return (
        are_drawn_over_each_other(first, second)
        and not first.encloses(second)
        and not second.encloses(first)
    )


def check_layout_geometry(
    layout: Layout,
    *,
    extents: Mapping[str, Extent],
    relations: Mapping[str, tuple[str, str]],
    members_of_box: Mapping[str, frozenset[str]],
) -> tuple[LayoutFinding, ...]:
    """Everything the geometry of *layout* decides.

    *extents* holds each placed element whose rectangle is known, by instance id; *relations* every
    relation the diagram draws with the instances at its ends, routed in the layout or not;
    *members_of_box* who is inside each box the layout sizes, at any depth.
    """
    findings: list[LayoutFinding] = []
    for key, route in layout.relations.items():
        if key in relations:
            findings.extend(_route_findings(key, route, relations[key], extents))
    findings.extend(
        LayoutFinding(LayoutDefect.CONNECTED_ELEMENTS_OVERLAP, (key, *ends))
        for key, ends in relations.items()
        if ends[0] != ends[1]
        and (first := extents.get(ends[0])) is not None
        and (second := extents.get(ends[1])) is not None
        and _overlap_as_a_conflict(first, second)
    )
    for box, placed in layout.boxes.items():
        box_extent = placed_extent(placed)
        if box_extent is None or box not in members_of_box:
            continue
        members = [extents[member] for member in members_of_box[box] if member in extents]
        findings.extend(
            LayoutFinding(LayoutDefect.BOX_HIDES_ELEMENT, (box, element))
            for element, extent in extents.items()
            if element not in members_of_box[box]
            # A part drawn inside a member is inside the box with it.
            and not any(member.encloses(extent) for member in members)
            and layout.z.get(element, 0) <= layout.z.get(box, 0)
            and are_drawn_over_each_other(box_extent, extent)
        )
    return tuple(findings)
