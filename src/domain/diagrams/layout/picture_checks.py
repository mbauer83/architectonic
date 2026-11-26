"""What a picture's geometry decides without anybody looking at it.

Every other check on a diagram reads its declarations or its body. Those are complete by
construction and blind to what a layout does with them: a body can be valid and still be drawn with
a line through a box it has nothing to do with. Whether two lines cross is a matter of taste and of
looking; four things are not, and they are decided here:

* a relation drawn **through** an element it does not join;
* two shapes drawn **over** each other;
* a label **wider** than the shape it labels;
* a box drawn **over** a shape that is not inside it;
* a relation drawn **through text**: a label, a box's title band, the diagram's title or legend;
* a relation that **bends at an end**, or **runs along** another line or a border — the hard rules
  of `route_quality` a reader needs to follow a line from one end to the other;
* a gap between two boxes **too narrow** for the lines that run along it (`channels`): where the
  room is the arrangement's, which no router can make;
* a relation that **leaves the smallest box holding both its ends** — a hard rule: two members of a
  box are joined inside it;
* a relation drawn with a **slanted** run: a router draws upright and level runs only, so a slant is
  a drawing that does not read back as the course it was drawn along.

Its soft rules — a jog, two decorations together — are counted beside the findings, like crossings.

Crossings and the worst detour are counted beside them as pointers for the eye, never as findings:
a dense view cannot avoid a crossing, and a count that failed one would teach authors to ignore it.

All of it is stated over extents — the rectangle a shape occupies — with a margin on every
question, so a line grazing a rounded corner or two boxes sharing a border are not reported.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations

from src.domain.diagrams.layout.channels import too_narrow
from src.domain.diagrams.layout.geometry import Extent, Point, course_length, crossings
from src.domain.diagrams.layout.rendered_picture import (
    DrawnBox,
    DrawnElement,
    DrawnRelation,
    RenderedPicture,
    extent_across,
)
from src.domain.diagrams.layout.route_quality import bends_at_ends, kinks, run_index, runs_along_in, square_course
from src.domain.diagrams.layout.routing.scene import run_for
from src.domain.diagrams.layout.text_clearance import runs_through_text, text_regions

#: How far inside an element a line must run before it counts as drawn through it. A line arriving
#: at a border, or passing a cut corner, stays within this.
_THROUGH_MARGIN = 2.0

#: How much two shapes must share, in each direction, before they count as drawn over each other.
#: Shapes that share a border, or whose strokes touch, share less.
_OVERLAP_MARGIN = 1.0

#: How far a label may reach past its shape's side and still count as within it: rounding, and the
#: half-stroke the outline is drawn with.
_LABEL_MARGIN = 1.0


class PictureDefect(StrEnum):
    """The four things a picture's geometry decides, in a reviewer's words."""

    RELATION_THROUGH_ELEMENT = "a relation drawn through an element it does not join"
    SHAPES_OVERLAP = "two shapes drawn over each other"
    LABEL_WIDER_THAN_SHAPE = "a label wider than its shape"
    BOX_OVER_NON_MEMBER = "a box drawn over a shape that is not inside it"
    RELATION_THROUGH_TEXT = "a relation drawn through text"
    BEND_AT_AN_END = "a relation that bends inside or right behind the decoration at one of its ends"
    RUNS_ALONG = "a relation running along another line or a border"
    NARROW_CHANNEL = "a gap between two boxes too narrow for the lines that run along it"
    LEAVES_ITS_BOX = "a relation that leaves the smallest box holding both its ends"
    SLANTED = "a relation drawn with a run neither upright nor level"


#: The defects only a router answers for: the hard rules of `route_quality` and `text_clearance`.
#: Decided of every picture, and asked only of one whose lines a router drew — GraphViz draws curves
#: into cluster title bands as a matter of course, which no author can repair.
KEPT_BY_THE_ROUTER = frozenset({
    PictureDefect.RELATION_THROUGH_TEXT, PictureDefect.BEND_AT_AN_END, PictureDefect.RUNS_ALONG,
    PictureDefect.NARROW_CHANNEL, PictureDefect.LEAVES_ITS_BOX, PictureDefect.SLANTED,
})


@dataclass(frozen=True)
class PictureFinding:
    """One place the picture is decidably wrong, by the aliases of the shapes it concerns.

    For a relation drawn through an element, *shapes* is the relation's two ends and then the
    element; through text, its two ends and then what the text is of — a box or an element, the two
    ends of the relation it labels, or nothing for the diagram's title or legend. For a narrow gap,
    the two boxes, the one with the lower coordinate first. For a relation leaving its box, its two
    ends and then the box. For the others it is the shapes
    themselves, the box first where one is a box.
    """

    defect: PictureDefect
    shapes: tuple[str, ...]
    #: For a narrow gap: how many lines run along it, and how many pixels wider it needs to be.
    lines: int = 0
    wider_by: int = 0


@dataclass(frozen=True)
class Detour:
    """How much longer than the straight line between its ends one relation is drawn."""

    ends: tuple[str, str]
    ratio: float


@dataclass(frozen=True)
class PictureReport:
    """What the geometry decides about one picture, and what it only counts."""

    findings: tuple[PictureFinding, ...]
    #: How many times two relations' lines pass through each other. Advisory.
    crossings: int
    #: The relation drawn least directly, or None where no relation joins two apart shapes. Advisory.
    worst_detour: Detour | None
    #: Jogs shorter than a readable segment, over every relation. Advisory: a soft rule.
    jogs: int = 0
    #: Pairs of end decorations drawn over each other. Advisory: a soft rule.
    heads_together: int = 0

    def of(self, defect: PictureDefect) -> tuple[PictureFinding, ...]:
        return tuple(finding for finding in self.findings if finding.defect is defect)


def _is_drawn_through(relation: DrawnRelation, extent: Extent) -> bool:
    interior = extent.shrunk_by(_THROUGH_MARGIN)
    if interior is None:
        return False
    course = relation.course
    return any(interior.is_entered_by(course[i], course[i + 1]) for i in range(len(course) - 1))


def _reach_of(course: Sequence[Point]) -> Extent:
    xs, ys = [point.x for point in course], [point.y for point in course]
    return Extent(min(xs), min(ys), max(xs), max(ys))


def _relations_through_elements(picture: RenderedPicture) -> list[PictureFinding]:
    """Each relation drawn through an element it does not join. An element outside the rectangle a
    relation's course spans is not asked: nothing of the course can enter it."""
    findings: list[PictureFinding] = []
    for relation in picture.relations:
        if not relation.course:
            continue
        reach = _reach_of(relation.course)
        findings += [
            PictureFinding(PictureDefect.RELATION_THROUGH_ELEMENT, (*relation.ends, element.alias))
            for element in picture.elements.values()
            if element.alias not in relation.ends
            and element.extent.left <= reach.right and reach.left <= element.extent.right
            and element.extent.top <= reach.bottom and reach.top <= element.extent.bottom
            and _is_drawn_through(relation, element.extent)
        ]
    return findings


def are_drawn_over_each_other(first: Extent, second: Extent) -> bool:
    shared = first.overlap_with(second)
    return shared is not None and shared.width > _OVERLAP_MARGIN and shared.height > _OVERLAP_MARGIN


def _overlapping_shapes(picture: RenderedPicture) -> list[PictureFinding]:
    """Elements over elements, and boxes over boxes where neither is drawn inside the other."""
    elements = [
        PictureFinding(PictureDefect.SHAPES_OVERLAP, (first.alias, second.alias))
        for first, second in combinations(picture.elements.values(), 2)
        if are_drawn_over_each_other(first.extent, second.extent)
    ]
    boxes = [
        PictureFinding(PictureDefect.SHAPES_OVERLAP, (first.alias, second.alias))
        for first, second in combinations(picture.boxes.values(), 2)
        if first.alias not in picture.boxes_around(second.alias)
        and second.alias not in picture.boxes_around(first.alias)
        and are_drawn_over_each_other(first.extent, second.extent)
    ]
    return elements + boxes


def _label_is_wider(shape: DrawnElement | DrawnBox) -> bool:
    """Whether the text set *inside* the shape reaches past its sides.

    Text set outside it is not asked about: a shape drawn as a symbol — an actor, a control, an
    interface — carries its label beneath, where it is as wide as it needs to be.
    """
    across = extent_across(
        tuple(word for word in shape.words if shape.extent.top <= word.start.y <= shape.extent.bottom)
    )
    if across is None:
        return False
    left, right = across
    return left < shape.extent.left - _LABEL_MARGIN or right > shape.extent.right + _LABEL_MARGIN


def _labels_wider_than_shapes(picture: RenderedPicture) -> list[PictureFinding]:
    return [
        PictureFinding(PictureDefect.LABEL_WIDER_THAN_SHAPE, (shape.alias,))
        for shape in (*picture.elements.values(), *picture.boxes.values())
        if _label_is_wider(shape)
    ]


def _boxes_over_non_members(picture: RenderedPicture) -> list[PictureFinding]:
    return [
        PictureFinding(PictureDefect.BOX_OVER_NON_MEMBER, (box.alias, element.alias))
        for box in picture.boxes.values()
        for element in picture.elements.values()
        if box.alias not in picture.boxes_around(element.alias)
        and are_drawn_over_each_other(box.extent, element.extent)
    ]


def _relations_through_text(picture: RenderedPicture) -> list[PictureFinding]:
    """Each relation and each text region it runs into, its own label among them."""
    regions = text_regions(picture, picture.surrounding)
    return [
        PictureFinding(PictureDefect.RELATION_THROUGH_TEXT, (*relation.ends, *region.of))
        for relation in picture.relations
        for region in regions
        if runs_through_text(relation.course, region.extent)
    ]


def _course_to_borders(relation: DrawnRelation, picture: RenderedPicture) -> tuple[Point, ...]:
    """A relation's line as a square course, carried on to the borders it stops short of for its decorations."""
    course = list(square_course(relation.path))
    if len(course) < 2:  # noqa: PLR2004 — a line has two ends
        return tuple(course)
    for at, before, end in ((0, 1, relation.ends[0]), (-1, -2, relation.ends[1])):
        extent = picture.extent_of(end)
        tip, behind = course[at], course[before]
        length = tip.distance_to(behind)
        if extent is None or length == 0:
            continue
        reach = extent.distance_to(tip)
        course[at] = Point(tip.x + (tip.x - behind.x) / length * reach, tip.y + (tip.y - behind.y) / length * reach)
    return tuple(course)


def _hard_to_follow(picture: RenderedPicture) -> list[PictureFinding]:
    """A and C of `route_quality`, for each relation of *picture*: its runs asked of one index of every
    line and border, built once (`run_index`), not of every other line once per line."""
    courses = [_course_to_borders(relation, picture) for relation in picture.relations]
    borders = [shape.extent for shape in (*picture.elements.values(), *picture.boxes.values())]
    runs = run_index(courses, borders)
    findings: list[PictureFinding] = []
    for index, (relation, course) in enumerate(zip(picture.relations, courses, strict=True)):
        decorated = (bool(relation.first_marks), bool(relation.second_marks))
        if bends_at_ends(course, decorated):
            findings.append(PictureFinding(PictureDefect.BEND_AT_AN_END, relation.ends))
        if runs_along_in(course, runs, index):
            findings.append(PictureFinding(PictureDefect.RUNS_ALONG, relation.ends))
    return findings


def _holding_both(picture: RenderedPicture, ends: tuple[str, str]) -> str | None:
    """The smallest box holding both *ends*, neither of them itself, or None."""
    extents = [extent for end in ends if (extent := picture.extent_of(end)) is not None]
    if len(extents) < len(ends):
        return None
    both = [
        (box.extent.width * box.extent.height, alias) for alias, box in picture.boxes.items()
        if alias not in ends and all(box.extent.encloses(extent) and box.extent != extent for extent in extents)
    ]
    return min(both)[1] if both else None


def _leaving_their_box(picture: RenderedPicture) -> list[PictureFinding]:
    """Each relation drawn outside the smallest box holding both its ends."""
    findings: list[PictureFinding] = []
    for relation in picture.relations:
        if (box := _holding_both(picture, relation.ends)) is None:
            continue
        inside = picture.boxes[box].extent
        if any(not inside.encloses(Extent(point.x, point.y, point.x, point.y), slack=_OVERLAP_MARGIN)
               for point in _course_to_borders(relation, picture)):
            findings.append(PictureFinding(PictureDefect.LEAVES_ITS_BOX, (*relation.ends, box)))
    return findings


#: How far off upright or level a run may be and still be drawn square: rounding of the written numbers.
_SQUARE = 0.5


def _is_slanted(course: tuple[Point, ...]) -> bool:
    return any(
        abs(a.x - b.x) > _SQUARE and abs(a.y - b.y) > _SQUARE for a, b in zip(course, course[1:], strict=False)
    )


def _slanted(picture: RenderedPicture) -> list[PictureFinding]:
    """Each relation whose line, read back, has a run neither upright nor level."""
    return [
        PictureFinding(PictureDefect.SLANTED, relation.ends)
        for relation in picture.relations if _is_slanted(square_course(relation.path))
    ]


def _narrow_channels(picture: RenderedPicture) -> list[PictureFinding]:
    """Each gap between two boxes too narrow for the lines drawn along it."""
    others = [
        *(element.extent for element in picture.elements.values()),
        *(region.extent for region in text_regions(picture, picture.surrounding)),
    ]
    courses = [_course_to_borders(relation, picture) for relation in picture.relations]
    ends = [
        (course[at], run_for(bool(marks)))
        for relation, course in zip(picture.relations, courses, strict=True) if len(course) > 1
        for at, marks in ((0, relation.first_marks), (-1, relation.second_marks))
    ]
    return [
        PictureFinding(PictureDefect.NARROW_CHANNEL, (channel.low, channel.high), channel.lines, channel.wider_by)
        for channel in too_narrow(
            {alias: box.extent for alias, box in picture.boxes.items()}, others, courses,
            {alias: element.extent for alias, element in picture.elements.items()}, ends,
        )
    ]


def _heads_together(picture: RenderedPicture) -> int:
    """How many pairs of end decorations, of different relations, are drawn over each other."""
    heads = [
        (index, around)
        for index, relation in enumerate(picture.relations)
        for mark in (*relation.first_marks, *relation.second_marks)
        if (around := Extent.around(mark.outline)) is not None
    ]
    return sum(
        1 for (first, one), (second, other) in combinations(heads, 2)
        if first != second and are_drawn_over_each_other(one, other)
    )


def _worst_detour(picture: RenderedPicture) -> Detour | None:
    detours = [
        Detour(ends=relation.ends, ratio=course_length(relation.course) / direct)
        for relation in picture.relations
        if relation.ends[0] != relation.ends[1]
        and (direct := relation.course[0].distance_to(relation.course[-1])) > 0
    ]
    return max(detours, key=lambda detour: detour.ratio, default=None)


def check_picture(picture: RenderedPicture) -> PictureReport:
    """Everything the geometry of *picture* decides, and the two things it counts."""
    return PictureReport(
        findings=(
            *_relations_through_elements(picture),
            *_overlapping_shapes(picture),
            *_labels_wider_than_shapes(picture),
            *_boxes_over_non_members(picture),
            *_relations_through_text(picture),
            *_hard_to_follow(picture),
            *_narrow_channels(picture),
            *_leaving_their_box(picture),
            *_slanted(picture),
        ),
        crossings=crossings([relation.course for relation in picture.relations]),
        worst_detour=_worst_detour(picture),
        jogs=sum(len(kinks(square_course(relation.path))) for relation in picture.relations),
        heads_together=_heads_together(picture),
    )
