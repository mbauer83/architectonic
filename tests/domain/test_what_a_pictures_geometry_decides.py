"""The four things a picture's geometry decides, and the two it only counts.

Stated over pictures built here as values, where the test owns every coordinate: each check is
shown the defect it reports and the nearest thing that is not one — a line arriving at a border, two
boxes sharing a side, a label set beneath a symbol — because a geometric check earns its keep by what
it does not report.
"""

from __future__ import annotations

import pytest

from src.domain.diagrams.layout.geometry import Extent, Point, courses_cross, segments_cross
from src.domain.diagrams.layout.picture_checks import PictureDefect, check_picture
from src.domain.diagrams.layout.rendered_picture import (
    DrawnBox,
    DrawnElement,
    DrawnRelation,
    MeasuredWord,
    RenderedPicture,
)


def _element(alias: str, left: float, top: float, *, inside: str | None = None, width: float = 100,
             height: float = 40, words: tuple[MeasuredWord, ...] = ()) -> DrawnElement:
    return DrawnElement(alias=alias, extent=Extent(left, top, left + width, top + height), inside=inside, words=words)


def _box(alias: str, extent: Extent, *, inside: str | None = None,
         words: tuple[MeasuredWord, ...] = ()) -> DrawnBox:
    return DrawnBox(alias=alias, extent=extent, inside=inside, words=words)


def _relation(first: str, second: str, *points: tuple[float, float]) -> DrawnRelation:
    course = tuple(Point(x, y) for x, y in points)
    return DrawnRelation(ends=(first, second), line_type="dependency", path=course, course=course)


def _picture(*shapes: DrawnElement | DrawnBox, relations: tuple[DrawnRelation, ...] = ()) -> RenderedPicture:
    return RenderedPicture(
        canvas=Extent(0, 0, 1000, 1000),
        elements={shape.alias: shape for shape in shapes if isinstance(shape, DrawnElement)},
        boxes={shape.alias: shape for shape in shapes if isinstance(shape, DrawnBox)},
        relations=relations,
    )


def _found(picture: RenderedPicture, defect: PictureDefect) -> list[tuple[str, ...]]:
    return [finding.shapes for finding in check_picture(picture).of(defect)]


class TestARelationDrawnThroughAnElement:
    _A, _B, _C = _element("A", 0, 0), _element("B", 400, 0), _element("C", 200, 0)

    def test_a_line_through_an_element_it_does_not_join_is_found(self) -> None:
        picture = _picture(self._A, self._B, self._C, relations=(_relation("A", "B", (100, 20), (400, 20)),))

        assert _found(picture, PictureDefect.RELATION_THROUGH_ELEMENT) == [("A", "B", "C")]

    def test_a_curve_is_followed_and_not_cut_across(self) -> None:
        """A course that bows around the element must not be judged by the chord between its ends."""
        around = _relation("A", "B", (100, 20), (150, 80), (250, 100), (350, 80), (400, 20))

        assert _found(_picture(self._A, self._B, self._C, relations=(around,)),
                      PictureDefect.RELATION_THROUGH_ELEMENT) == []

    def test_a_line_arriving_at_its_own_ends_is_not_through_them(self) -> None:
        into_both = _relation("A", "B", (50, 20), (450, 20))

        assert _found(_picture(self._A, self._B, relations=(into_both,)),
                      PictureDefect.RELATION_THROUGH_ELEMENT) == []

    def test_a_line_along_an_elements_border_is_not_through_it(self) -> None:
        grazing = _relation("A", "B", (100, 41), (400, 41))

        assert _found(_picture(self._A, self._B, self._C, relations=(grazing,)),
                      PictureDefect.RELATION_THROUGH_ELEMENT) == []

    def test_a_line_through_a_box_is_not_a_finding(self) -> None:
        """A relation into a box's member has to cross the box; only elements are in a line's way."""
        box = _box("G", Extent(180, -20, 320, 80))

        picture = _picture(self._A, self._B, box, relations=(_relation("A", "B", (100, 20), (400, 20)),))

        assert check_picture(picture).findings == ()


class TestShapesDrawnOverEachOther:
    def test_two_elements_sharing_ground_are_found(self) -> None:
        picture = _picture(_element("A", 0, 0), _element("B", 60, 20))

        assert _found(picture, PictureDefect.SHAPES_OVERLAP) == [("A", "B")]

    def test_two_elements_sharing_a_border_are_not(self) -> None:
        assert check_picture(_picture(_element("A", 0, 0), _element("B", 100, 0))).findings == ()

    def test_two_elements_whose_strokes_touch_are_not(self) -> None:
        """Half a pixel shared is two outlines drawn against each other, not one shape over another."""
        assert check_picture(_picture(_element("A", 0, 0), _element("B", 99.5, 0))).findings == ()

    def test_a_box_and_the_box_inside_it_are_not(self) -> None:
        outer = _box("OUTER", Extent(0, 0, 400, 400))
        inner = _box("INNER", Extent(20, 20, 200, 200), inside="OUTER")
        innermost = _box("INNERMOST", Extent(30, 30, 100, 100), inside="INNER")

        assert check_picture(_picture(outer, inner, innermost)).findings == ()

    def test_two_boxes_neither_inside_the_other_are_found(self) -> None:
        picture = _picture(_box("G1", Extent(0, 0, 200, 200)), _box("G2", Extent(150, 150, 400, 400)))

        assert _found(picture, PictureDefect.SHAPES_OVERLAP) == [("G1", "G2")]


class TestALabelWiderThanItsShape:
    def test_text_reaching_past_the_side_is_found(self) -> None:
        wide = _element("A", 0, 0, words=(MeasuredWord("Much too long", Point(10, 24), 130),))

        assert _found(_picture(wide), PictureDefect.LABEL_WIDER_THAN_SHAPE) == [("A",)]

    def test_text_starting_before_the_side_is_found_on_a_box_too(self) -> None:
        box = _box("G", Extent(100, 0, 200, 200), words=(MeasuredWord("«ApplicationGrouping»", Point(60, 14), 180),))

        assert _found(_picture(box), PictureDefect.LABEL_WIDER_THAN_SHAPE) == [("G",)]

    def test_text_that_fits_is_not(self) -> None:
        words = (MeasuredWord("Fits", Point(10, 24), 80), MeasuredWord("too", Point(10, 36), 90))
        fits = _element("A", 0, 0, words=words)

        assert check_picture(_picture(fits)).findings == ()

    def test_text_set_beneath_a_symbol_is_not_asked_about(self) -> None:
        """An actor or a control is a small symbol with its name under it, as wide as it needs to be.
        Reported once against a real control-structure diagram before this was a rule."""
        beneath = (MeasuredWord("Open store / release key", Point(30, 44), 170),)
        symbol = _element("A", 100, 0, width=24, height=24, words=beneath)

        assert check_picture(_picture(symbol)).findings == ()


class TestABoxOverAShapeThatIsNotInsideIt:
    _BOX = _box("G", Extent(0, 0, 300, 300))

    def test_an_element_drawn_under_a_box_it_is_not_in_is_found(self) -> None:
        picture = _picture(self._BOX, _element("STRAY", 250, 250))

        assert _found(picture, PictureDefect.BOX_OVER_NON_MEMBER) == [("G", "STRAY")]

    def test_a_member_is_not_and_neither_is_a_member_of_a_box_inside(self) -> None:
        inner = _box("INNER", Extent(10, 10, 200, 200), inside="G")
        member = _element("M", 220, 220, width=50, inside="G")
        picture = _picture(self._BOX, inner, member, _element("N", 20, 20, inside="INNER"))

        assert check_picture(picture).findings == ()

    def test_an_element_beside_the_box_is_not(self) -> None:
        assert check_picture(_picture(self._BOX, _element("BESIDE", 300, 0))).findings == ()


class TestWhatIsOnlyCounted:
    _SHAPES = (_element("A", 0, 0), _element("B", 400, 400), _element("C", 400, 0), _element("D", 0, 400))

    def test_two_lines_passing_through_each_other_are_one_crossing_and_no_finding(self) -> None:
        picture = _picture(*self._SHAPES, relations=(
            _relation("A", "B", (100, 40), (400, 400)),
            _relation("C", "D", (400, 40), (100, 400)),
        ))

        report = check_picture(picture)

        assert report.crossings == 1
        assert report.findings == ()

    def test_two_lines_leaving_one_point_do_not_cross(self) -> None:
        picture = _picture(*self._SHAPES, relations=(
            _relation("A", "B", (100, 40), (400, 400)),
            _relation("A", "C", (100, 40), (400, 20)),
        ))

        assert check_picture(picture).crossings == 0

    def test_the_worst_detour_is_the_relation_drawn_least_directly(self) -> None:
        direct = _relation("A", "C", (100, 20), (400, 20))
        roundabout = _relation("A", "D", (50, 40), (50, 200), (300, 200), (300, 380), (50, 380), (50, 400))

        detour = check_picture(_picture(*self._SHAPES, relations=(direct, roundabout))).worst_detour

        assert detour is not None
        assert detour.ends == ("A", "D")
        assert detour.ratio == pytest.approx((160 + 250 + 180 + 250 + 20) / 360)

    def test_a_relation_from_a_shape_to_itself_has_no_detour(self) -> None:
        loop = _relation("A", "A", (100, 10), (140, 10), (140, 30), (100, 30))

        assert check_picture(_picture(*self._SHAPES, relations=(loop,))).worst_detour is None

    def test_a_picture_with_no_relations_counts_nothing(self) -> None:
        report = check_picture(_picture(*self._SHAPES))

        assert (report.crossings, report.worst_detour) == (0, None)


class TestTheGeometryUnderneath:
    def test_segments_that_only_touch_at_an_end_do_not_cross(self) -> None:
        assert not segments_cross(Point(0, 0), Point(10, 0), Point(10, 0), Point(10, 10))
        assert segments_cross(Point(0, 0), Point(10, 10), Point(0, 10), Point(10, 0))

    def test_a_course_can_cross_another_more_than_once(self) -> None:
        zigzag = (Point(0, -5), Point(10, 5), Point(20, -5), Point(30, 5))

        assert courses_cross(zigzag, (Point(-10, 0), Point(40, 0))) == 3

    def test_an_extent_is_entered_only_by_a_segment_with_a_point_inside(self) -> None:
        extent = Extent(10, 10, 20, 20)

        assert extent.is_entered_by(Point(0, 15), Point(30, 15))
        assert extent.is_entered_by(Point(12, 12), Point(14, 14)), "a segment wholly inside is inside"
        assert not extent.is_entered_by(Point(0, 0), Point(30, 5))
        assert not extent.is_entered_by(Point(0, 15), Point(5, 15)), "a segment that stops short does not enter"

    def test_the_boxes_around_a_shape_are_innermost_first(self) -> None:
        picture = _picture(
            _box("OUTER", Extent(0, 0, 400, 400)), _box("INNER", Extent(10, 10, 200, 200), inside="OUTER"),
            _element("E", 20, 20, inside="INNER"),
        )

        assert list(picture.boxes_around("E")) == ["INNER", "OUTER"]
        assert list(picture.boxes_around("OUTER")) == []
