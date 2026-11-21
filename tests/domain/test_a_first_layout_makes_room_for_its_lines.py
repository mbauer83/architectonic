"""A first layout opens every gap too narrow for its lines, and moves nothing else out of its order.

The renderer's arrangement leaves gaps made for curves; the router lays lines along them, and where
more lines run along a gap than fit at nudging's spacing they end up along each other or along a
border, which no router can repair. Widening is the one place room is made (`routing.widening`),
over the one reading of gaps (`channels`) the picture check (W384) also uses.
"""

from __future__ import annotations

from src.domain.diagrams.layout.channels import Channel, channels, parents_of, too_narrow
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.route_quality import END_RUN
from src.domain.diagrams.layout.routing.router import route_all
from src.domain.diagrams.layout.routing.scene import IDEAL_SEPARATION, Connector, RoutingScene
from src.domain.diagrams.layout.routing.widening import narrow_channels, widened
from tests.support.routing_fixtures import widening_scene

_LEFT, _RIGHT = Extent(0, 0, 200, 300), Extent(220, 0, 420, 300)


def _upright(x: float) -> tuple[Point, ...]:
    return (Point(x, -50), Point(x, 350))


def test_a_gap_is_measured_by_the_lines_that_run_along_it_not_those_crossing_it() -> None:
    along = [_upright(205), _upright(215)]
    crossing = [(Point(100, 150), Point(300, 150))]

    found = channels({"left": _LEFT, "right": _RIGHT}, [], [*along, *crossing])

    assert [(one.low, one.high, one.across, one.lines) for one in found] == [("left", "right", "x", 2)]


def test_a_gap_holds_its_lines_at_nudging_s_spacing_from_each_border_and_each_other() -> None:
    gap = Channel("left", "right", "x", 200, 220, 0, 300, lines=2)

    assert gap.wider_by == 3 * IDEAL_SEPARATION - 20 - 1  # a pixel of a layout's rounding allowed
    assert Channel("left", "right", "x", 200, 236, 0, 300, lines=2).wider_by == 0
    assert Channel("left", "right", "x", 200, 201, 0, 300, lines=0).wider_by == 0


def test_a_gap_something_else_stands_in_is_no_channel() -> None:
    standing = Extent(202, 100, 218, 140)

    assert channels({"left": _LEFT, "right": _RIGHT}, [standing], [_upright(210)]) == []


def test_a_box_and_the_border_of_the_box_it_sits_in_face_each_other() -> None:
    boxes = {"outer": Extent(0, 0, 500, 400), "inner": Extent(20, 40, 480, 380)}

    found = {(one.low, one.high, one.across) for one in channels(boxes, [], [])}

    assert parents_of(boxes) == {"outer": None, "inner": "outer"}
    assert found == {("outer", "inner", "x"), ("inner", "outer", "x"), ("outer", "inner", "y"),
                     ("inner", "outer", "y")}


def test_widening_opens_every_narrow_gap_and_keeps_order_nesting_and_sizes() -> None:
    scene, connectors = widening_scene()
    assert narrow_channels(scene, connectors)

    room = widened(scene, connectors)

    assert narrow_channels(room, connectors) == []
    for key, extent in scene.elements.items():
        assert (room.elements[key].width, room.elements[key].height) == (extent.width, extent.height), key
    for key, box in scene.boxes.items():
        for other, other_box in scene.boxes.items():
            assert box.encloses(other_box) == room.boxes[key].encloses(room.boxes[other]), (key, other)
            assert (box.right <= other_box.left) == (room.boxes[key].right <= room.boxes[other].left), (key, other)
            assert (box.bottom <= other_box.top) == (room.boxes[key].bottom <= room.boxes[other].top), (key, other)
        for element, extent in scene.elements.items():
            assert box.encloses(extent) == room.boxes[key].encloses(room.elements[element]), (key, element)


def test_a_box_s_padding_grows_until_the_run_into_an_arrowhead_starts_inside_it() -> None:
    """Value Stream: arrows into Model & Validate began their straight run outside the Deliver box,
    whose padding was narrower than the run. The run is the arrowhead's readability (rule A), so the
    room is made, not the run shortened."""
    scene = RoutingScene(
        elements={"member": Extent(124, 100, 224, 140), "outside": Extent(-300, 100, -200, 140)},
        boxes={"box": Extent(100, 60, 400, 300)},
    )
    connectors = [Connector("in", "outside", "member")]
    assert narrow_channels(scene, connectors)

    room = widened(scene, connectors)

    assert room.elements["member"].left - room.boxes["box"].left >= END_RUN + IDEAL_SEPARATION - 1
    assert narrow_channels(room, connectors) == []


def test_an_arrangement_with_room_enough_is_not_moved() -> None:
    scene = RoutingScene(
        elements={"a": Extent(40, 40, 140, 80), "b": Extent(300, 40, 400, 80)},
        boxes={"left": Extent(0, 0, 180, 120), "right": Extent(260, 0, 440, 120)},
    )
    connectors: list[Connector] = []

    assert widened(scene, connectors) == scene


def test_the_strategy_overview_s_narrow_row_is_widened_until_its_lines_fit() -> None:
    """The defect that asked for this: lines from a row of capabilities to the row of resources and
    value streams below it all ran along the 32 px between the rows and the 27 px between the two
    lower boxes, so seven of them ran along each other or a border."""
    elements = {
        **{f"cap{index}": Extent(620 + index * 200, 580, 780 + index * 200, 620) for index in range(5)},
        "res0": Extent(60, 830, 240, 870), "res1": Extent(700, 830, 880, 870),
        "val0": Extent(1140, 830, 1320, 870), "val1": Extent(1800, 830, 1980, 870),
    }
    boxes = {
        "strategy": Extent(7, 364, 2133, 924), "capabilities": Extent(588, 536, 1624, 768),
        "resources": Extent(31, 800, 1092, 900), "values": Extent(1119, 800, 2109, 900),
    }
    pairs = [(f"cap{index}", end) for index in range(5) for end in ("res0", "res1", "val0", "val1")]
    connectors = [Connector(f"r{number}", source, target) for number, (source, target) in enumerate(pairs)]
    scene = RoutingScene(elements=elements, boxes=boxes)
    before = route_all(scene, connectors)
    assert too_narrow(boxes, list(elements.values()), [routed.course for routed in before.routes.values()])

    room = widened(scene, connectors)

    assert narrow_channels(room, connectors) == []
