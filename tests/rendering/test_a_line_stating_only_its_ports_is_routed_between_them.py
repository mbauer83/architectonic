"""A line whose layout states its ports and no bends is routed between those ports, round what is in the way.

A straightened line keeps its ports and loses its bends (`layout_intents._straightened`). The composer used
to read any route with two stated ports as a whole route, completed at right angles straight through
whatever lay between them, so *Straighten* drew a line through the element in its way. Its bends are
unstated, so they are the router's; a route that states its bends still runs exactly them.
"""

from __future__ import annotations

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Layout, Placed, Port, Route, Side
from src.domain.diagrams.layout.rendered_picture import DrawnElement, DrawnRelation, RenderedPicture
from src.infrastructure.rendering.layout.arrangement import arrange

#: A source and a target level with each other, and an element between them on the straight run.
_SHAPES = {"a": Extent(40, 100, 140, 140), "between": Extent(260, 90, 340, 150), "b": Extent(460, 100, 560, 140)}
_PORTS = Route(source=Port(Side.RIGHT, 0.5), target=Port(Side.LEFT, 0.5))


def _picture() -> RenderedPicture:
    path = (Point(140, 120), Point(460, 120))
    return RenderedPicture(
        canvas=Extent(0, 0, 700, 300),
        elements={alias: DrawnElement(alias, extent, None) for alias, extent in _SHAPES.items()},
        boxes={},
        relations=(DrawnRelation(ends=("a", "b"), line_type="dependency", path=path, course=path, words=()),),
    )


def _arranged(route: Route) -> tuple[Point, ...]:
    diagram = LaidOutDiagram(
        Layout(elements={"a-id": Placed(40, 100)}, relations={"r": route}),
        instance_by_alias={"a": "a-id", "between": "between-id", "b": "b-id"},
        relations={"r": ("a", "b")},
    )
    arrangement = arrange(_picture(), diagram)
    assert arrangement.unroutable == ()
    return arrangement.relations[0].course


def _crosses(course: tuple[Point, ...], extent: Extent) -> bool:
    return any(
        min(one.x, other.x) < extent.right and max(one.x, other.x) > extent.left
        and min(one.y, other.y) < extent.bottom and max(one.y, other.y) > extent.top
        for one, other in zip(course, course[1:], strict=False)
    )


def test_a_line_stating_only_its_ports_leaves_and_arrives_by_them_and_goes_round() -> None:
    course = _arranged(_PORTS)

    assert course[0] == Point(140, 120)
    assert course[-1] == Point(460, 120)
    assert not _crosses(course, _SHAPES["between"])


def test_a_line_stating_its_bends_runs_exactly_them() -> None:
    bent = Route(source=_PORTS.source, target=_PORTS.target, via=((200, 120), (200, 200), (400, 200), (400, 120)))

    course = _arranged(bent)

    assert course == (
        Point(140, 120), Point(200, 120), Point(200, 200), Point(400, 200), Point(400, 120), Point(460, 120),
    )
