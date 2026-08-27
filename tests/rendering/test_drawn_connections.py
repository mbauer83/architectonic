"""What `drawn_connections` sees in a picture, stated over hand-authored geometry.

Fixtures rather than committed PlantUML output, and deliberately: an SVG from the renderer is a few
hundred elements whose defect is one arrowhead among twenty, so a fixture that broke would not say
which rule broke. Each SVG here is the smallest drawing that exhibits exactly one thing.

The geometry is the real geometry: coordinates, tolerances and shape kinds are those PlantUML emits,
so a rule tuned against these stays tuned against the renderer. The pairing was checked — every rule
below was also observed on real rendered output before it was written down here.
"""

from __future__ import annotations

from src.infrastructure.rendering.drawn_connections import Disconnection, drawn_picture


def _svg(*body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">'
        + "".join(body)
        + "</svg>"
    )


def _step(x: float, y: float, w: float = 80, h: float = 30) -> str:
    return f'<rect fill="#F1F1F1" x="{x}" y="{y}" width="{w}" height="{h}"/>'


def _line(x1: float, y1: float, x2: float, y2: float) -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>'


def _head_pointing_down(x: float, y: float) -> str:
    """An arrowhead whose tip is at (x, y), pointing downwards — PlantUML's proportions."""
    return f'<polygon fill="#181818" points="{x - 4},{y - 9} {x + 4},{y - 9} {x},{y}"/>'


def _head_pointing_left(x: float, y: float) -> str:
    return f'<polygon fill="#181818" points="{x + 9},{y - 4} {x + 9},{y + 4} {x},{y}"/>'


def _head_pointing_up(x: float, y: float) -> str:
    return f'<polygon fill="#181818" points="{x - 4},{y + 9} {x + 4},{y + 9} {x},{y}"/>'


def test_an_arrow_arriving_at_a_step_is_not_a_defect() -> None:
    picture = drawn_picture(_svg(_step(60, 100), _line(100, 40, 100, 100), _head_pointing_down(100, 100)))
    assert picture.defects == ()
    assert picture.arrowheads_examined == 1
    assert picture.shapes_found == 1


def test_an_arrow_into_empty_space_reaches_nothing() -> None:
    """The arrowhead touches no shape and no line: the flow stops in mid-air."""
    picture = drawn_picture(_svg(_step(60, 20), _line(100, 50, 100, 90), _head_pointing_down(100, 200)))
    assert [d.disconnection for d in picture.defects] == [Disconnection.REACHES_NOTHING]
    assert picture.defects[0].at == (100.0, 200.0)


def test_an_arrow_landing_partway_along_a_crosswise_line_reaches_another_arrow() -> None:
    """The shape that shipped: an arm merges into another edge, so control's destination is a guess."""
    picture = drawn_picture(_svg(
        _step(200, 20),
        _line(40, 60, 40, 300),      # a long vertical edge running elsewhere
        _line(240, 150, 40, 150),    # the arm, arriving at its middle
        _head_pointing_left(40, 150),
    ))
    assert [d.disconnection for d in picture.defects] == [Disconnection.REACHES_ANOTHER_ARROW]


def test_a_direction_marker_partway_along_its_own_line_is_not_a_defect() -> None:
    """PlantUML marks which way a long return edge runs. It decorates its own path, so it arrives
    nowhere and must not be reported — the distinction is that the line is collinear with the tip."""
    picture = drawn_picture(_svg(
        _step(60, 20),
        _line(300, 300, 300, 60),
        _head_pointing_up(300, 180),
    ))
    assert picture.defects == ()
    assert picture.arrowheads_examined == 1


def test_an_arrow_arriving_where_two_segments_meet_is_not_a_defect() -> None:
    """A corner in one routed path is not a merge into another: the tip is at a segment's end."""
    picture = drawn_picture(_svg(
        _step(60, 200),
        _line(300, 60, 300, 150),
        _line(300, 150, 100, 150),
        _line(100, 150, 100, 200),
        _head_pointing_down(100, 200),
    ))
    assert picture.defects == ()


def test_a_line_through_a_shape_crosses_it() -> None:
    """A return edge routed over the box it returns to — five of these shipped in one shape."""
    picture = drawn_picture(_svg(_step(60, 100), _line(100, 40, 100, 300)))
    assert [d.disconnection for d in picture.defects] == [Disconnection.CROSSES_A_SHAPE]
    assert "runs through the shape" in picture.defects[0].detail


def test_a_line_stopping_at_a_shapes_edge_does_not_cross_it() -> None:
    picture = drawn_picture(_svg(_step(60, 100), _line(100, 40, 100, 100)))
    assert picture.defects == ()


def test_a_merge_diamond_is_a_shape_an_arrow_can_arrive_at() -> None:
    """Four corners, like an arrowhead, and separated from one by area: a bare merge diamond is the
    smallest shape PlantUML draws, and an arrow arriving at it arrives somewhere."""
    diamond = '<polygon fill="#F1F1F1" points="90,150 110,165 90,180 70,165"/>'
    picture = drawn_picture(_svg(diamond, _line(90, 100, 90, 150), _head_pointing_down(90, 150)))
    assert picture.defects == ()
    assert picture.shapes_found == 1
    assert picture.arrowheads_examined == 1


def test_a_picture_drawn_with_curves_reports_that_it_examined_nothing() -> None:
    """A caller reading only `defects` would take this for health; `arrowheads_examined` says
    otherwise, which is why it is part of the answer."""
    picture = drawn_picture(_svg('<path d="M10,10 C20,20 30,30 40,40"/>'))
    assert picture.defects == ()
    assert picture.arrowheads_examined == 0


def test_something_that_is_not_a_picture_is_a_different_problem() -> None:
    try:
        drawn_picture("not svg at all")
    except ValueError as exc:
        assert "not a valid SVG document" in str(exc)
    else:  # pragma: no cover — the raise is the contract
        raise AssertionError("expected ValueError")
