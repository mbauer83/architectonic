"""The composer writes drawing markup and the reader reads it back: the pair, over what the syntax permits.

`svg_path_data` both reads a path's `d` and writes one with its points moved; `svg_markup` moves every
kind of drawing PlantUML makes. Stated over every command the reader accepts — not only those
PlantUML happens to emit for today's notation — with the points checked where they were put.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

import pytest

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import EndMark, MarkShape
from src.domain.diagrams.layout.route_quality import square_course
from src.infrastructure.rendering.layout._svg_drawing import SVG_NAMESPACE, outline_extent
from src.infrastructure.rendering.layout.relation_decorations import frame_as_drawn
from src.infrastructure.rendering.layout.relation_drawing import rounded_path
from src.infrastructure.rendering.layout.svg_markup import Motion, drawn_extent, fitted, moved
from src.infrastructure.rendering.layout.svg_path_data import moved_path, read_path

_PATHS = (
    "M10,20 L30,20 L30,40 Z",
    "M0,0 C10,0 20,10 20,20",
    "M5,5 Q15,5 15,15",
    "M1.5,2.25 L3.125,4 L-7,8.5",
    "M0,0 A3.1,3.1 0 0 1 8.6,0",
    "M0,0 L1,1 L2,2 M5,5 L6,6",
    "M0 0 L1e1 0 L10 1.5e1",
)


@pytest.mark.parametrize("d", _PATHS)
def test_a_path_written_back_unmoved_reads_as_it_did(d: str) -> None:
    assert read_path(moved_path(d, lambda x, y: (x, y))) == read_path(d)


@pytest.mark.parametrize("d", _PATHS)
def test_every_point_of_a_moved_path_is_where_the_move_put_it(d: str) -> None:
    shifted = read_path(moved_path(d, lambda x, y: (x + 7.5, y - 3)))

    assert shifted.through == tuple(Point(point.x + 7.5, point.y - 3) for point in read_path(d).through)


@pytest.mark.parametrize(
    "course",
    [
        ((0, 0), (100, 0), (100, 7), (300, 7)),
        ((0, 0), (100, 0), (100, 2), (300, 2), (300, 80)),
        ((0, 0), (0, 50), (12, 50), (12, 90)),
        ((0, 0), (40, 0)),
    ],
)
def test_a_rounded_line_reads_back_as_the_runs_it_was_drawn_along(course: tuple[tuple[float, float], ...]) -> None:
    """A 7 px jog was drawn as two curves meeting, and read back as a slanted run: the writer and the
    reader of a relation's line, held to each other over short runs between bends."""
    points = tuple(Point(x, y) for x, y in course)

    assert square_course(read_path(rounded_path(points)).through) == points


def _svg(tag: str, **attributes: str) -> Element:
    return Element(f"{{{SVG_NAMESPACE}}}{tag}", attributes)


@pytest.mark.parametrize(
    "drawing",
    [
        _svg("rect", x="10", y="20", width="30", height="40"),
        _svg("ellipse", cx="5", cy="6", rx="2", ry="3"),
        _svg("polygon", points="0,0,10,0,10,10"),
        _svg("path", d="M0,0 L10,0 L10,10"),
        _svg("image", x="1", y="2", width="8", height="8"),
        _svg("line", x1="0", y1="0", x2="4", y2="9"),
    ],
)
def test_a_shifted_drawing_occupies_its_old_rectangle_shifted(drawing: Element) -> None:
    was = drawn_extent(drawing)
    now = drawn_extent(moved(drawing, Motion.shift(100, -20)))

    assert was is not None
    assert now == Extent(was.left + 100, was.top - 20, was.right + 100, was.bottom - 20)


def test_a_quarter_turn_turns_a_decoration_to_face_the_new_way() -> None:
    """An arrowhead pointing down, carried to a line arriving from the left, points right."""
    head = _svg("polygon", points="0,0,4,-9,-4,-9")
    turned = moved(head, Motion.facing(Point(0, 0), (0.0, 1.0), Point(50, 50), (1.0, 0.0)))

    assert outline_extent(turned) == Extent(41, 46, 50, 54)


def test_an_outline_fitted_to_a_new_rectangle_keeps_its_corners_as_drawn() -> None:
    """A cut corner stays the size it was drawn, whatever the new size."""
    octagon = _svg("path", d="M10,0 L90,0 L100,10 L100,30 L90,40 L10,40 L0,30 L0,10 Z")
    stretched = fitted(octagon, Extent(0, 0, 100, 40), Extent(200, 100, 260, 220))

    points = read_path(stretched.get("d") or "").through
    assert Point(210, 100) in points
    assert Point(250, 220) in points
    assert outline_extent(stretched) == Extent(200, 100, 260, 220)


def test_a_decoration_s_frame_is_read_off_the_decoration_not_off_the_hook_in_the_line() -> None:
    """The line PlantUML drew into Dogfood's left side hooked upwards in its last pixels; a frame taken
    from that hook put the arrowhead 15 px below the element once it was carried to a new end."""
    element = Extent(100, 0, 200, 40)
    hooked = (Point(0, 20), Point(80, 20), Point(84, 18), Point(88, 14))  # the line's last run turns up
    head = EndMark(MarkShape.POLYGON, (Point(100, 20), Point(91, 16), Point(91, 24)), filled=True)

    frame = frame_as_drawn((head,), hooked, element)

    assert frame.at == Point(100, 20)
    assert frame.heading == pytest.approx((1.0, 0.0))
