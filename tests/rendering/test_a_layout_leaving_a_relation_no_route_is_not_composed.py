"""A layout that leaves a relation no route is arranged with that relation named — never a crash.

The arrangement used to label every relation before anything looked at which were unroutable, and
labelling one that has no course raised a `KeyError`. The composer never got to answer `NotComposed`:
a stored picture fell back on the exception, and a request for the server's picture of
a layout answered 500 (seen on a real diagram once two moves and a resize walled an element in).
"""

from __future__ import annotations

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Layout, Placed
from src.domain.diagrams.layout.rendered_picture import DrawnElement, DrawnRelation, MeasuredWord, RenderedPicture
from src.infrastructure.rendering.layout.arrangement import arrange

#: An element walled in on every side by four others, and one far away it is related to.
_SHAPES = {
    "walled": Extent(100, 100, 160, 130), "north": Extent(90, 70, 170, 90), "south": Extent(90, 140, 170, 160),
    "west": Extent(60, 90, 90, 140), "east": Extent(170, 90, 200, 140), "far": Extent(500, 100, 560, 130),
}


def _picture() -> RenderedPicture:
    path = (Point(160, 115), Point(500, 115))
    return RenderedPicture(
        canvas=Extent(0, 0, 700, 300),
        elements={alias: DrawnElement(alias, extent, None) for alias, extent in _SHAPES.items()},
        boxes={},
        relations=(
            DrawnRelation(
                ends=("walled", "far"), line_type="dependency", path=path, course=path,
                words=(MeasuredWord("serves", Point(300, 110), 40.0),),
            ),
        ),
    )


def test_the_relation_no_route_reaches_is_named_rather_than_labelled() -> None:
    # The far element moved, so the line is routed rather than kept as drawn.
    diagram = LaidOutDiagram(
        Layout(elements={"far-id": Placed(520, 100)}),
        instance_by_alias={"far": "far-id"},
        relations={"r": ("walled", "far")},
    )

    arrangement = arrange(_picture(), diagram)

    assert arrangement.unroutable == ("walled and far",)
    assert arrangement.relations == ()
