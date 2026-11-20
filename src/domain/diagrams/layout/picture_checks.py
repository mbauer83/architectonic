"""What a picture's geometry decides without anybody looking at it.

Every other check on a diagram reads its declarations or its body. Those are complete by
construction and blind to what a layout does with them: a body can be valid and still be drawn with
a line through a box it has nothing to do with. Whether two lines cross is a matter of taste and of
looking; four things are not, and they are decided here:

* a relation drawn **through** an element it does not join;
* two shapes drawn **over** each other;
* a label **wider** than the shape it labels;
* a box drawn **over** a shape that is not inside it.

Crossings and the worst detour are counted beside them as pointers for the eye, never as findings:
a dense view cannot avoid a crossing, and a count that failed one would teach authors to ignore it.

All of it is stated over extents — the rectangle a shape occupies — with a margin on every
question, so a line grazing a rounded corner or two boxes sharing a border are not reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations

from src.domain.diagrams.layout.geometry import Extent, course_length, courses_cross
from src.domain.diagrams.layout.rendered_picture import (
    DrawnBox,
    DrawnElement,
    DrawnRelation,
    RenderedPicture,
    extent_across,
)

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


@dataclass(frozen=True)
class PictureFinding:
    """One place the picture is decidably wrong, by the aliases of the shapes it concerns.

    For a relation drawn through an element, *shapes* is the relation's two ends and then the
    element; for the others it is the shapes themselves, the box first where one is a box.
    """

    defect: PictureDefect
    shapes: tuple[str, ...]


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

    def of(self, defect: PictureDefect) -> tuple[PictureFinding, ...]:
        return tuple(finding for finding in self.findings if finding.defect is defect)


def _is_drawn_through(relation: DrawnRelation, extent: Extent) -> bool:
    interior = extent.shrunk_by(_THROUGH_MARGIN)
    if interior is None:
        return False
    course = relation.course
    return any(interior.is_entered_by(course[i], course[i + 1]) for i in range(len(course) - 1))


def _relations_through_elements(picture: RenderedPicture) -> list[PictureFinding]:
    return [
        PictureFinding(PictureDefect.RELATION_THROUGH_ELEMENT, (*relation.ends, element.alias))
        for relation in picture.relations
        for element in picture.elements.values()
        if element.alias not in relation.ends and _is_drawn_through(relation, element.extent)
    ]


def _are_drawn_over_each_other(first: Extent, second: Extent) -> bool:
    shared = first.overlap_with(second)
    return shared is not None and shared.width > _OVERLAP_MARGIN and shared.height > _OVERLAP_MARGIN


def _overlapping_shapes(picture: RenderedPicture) -> list[PictureFinding]:
    """Elements over elements, and boxes over boxes where neither is drawn inside the other."""
    elements = [
        PictureFinding(PictureDefect.SHAPES_OVERLAP, (first.alias, second.alias))
        for first, second in combinations(picture.elements.values(), 2)
        if _are_drawn_over_each_other(first.extent, second.extent)
    ]
    boxes = [
        PictureFinding(PictureDefect.SHAPES_OVERLAP, (first.alias, second.alias))
        for first, second in combinations(picture.boxes.values(), 2)
        if first.alias not in picture.boxes_around(second.alias)
        and second.alias not in picture.boxes_around(first.alias)
        and _are_drawn_over_each_other(first.extent, second.extent)
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
        and _are_drawn_over_each_other(box.extent, element.extent)
    ]


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
        ),
        crossings=sum(
            courses_cross(first.course, second.course)
            for first, second in combinations(picture.relations, 2)
        ),
        worst_detour=_worst_detour(picture),
    )
