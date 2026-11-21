"""The router as cases, for `tests/fixtures/layout_geometry/routing.json`.

Each case is a scene, its connectors and what `route_all` answers — every route's ports and course,
the unroutable connectors and the pairs nudging could not separate. The TypeScript router is run on
the same scenes and must answer the same, to the pixel: the two are one algorithm by this file.

The cases are chosen so each stage decides something: a straight run, a way round an element, round
a title band, into and out of nested boxes, many routes through one channel for nudging, a whole and
its part, a loop, two elements too close for a stub, an element walled in so no route reaches it, and
a drag's quick pass over a moved element.

`widening` pins the room a first layout makes: one scene's channels, how many lines run along each
and how much wider each needs to be, and the scene widened.

`graph` pins the visibility graph itself for one scene: its segments, each stopping at the first
obstacle, and every join once a search's terminals are joined to it. The routes rest on it, so the two
languages building one graph is what the cases above rely on.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence

from src.domain.diagrams.layout.channels import channels
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Side
from src.domain.diagrams.layout.routing.graph import EAST, SOUTH
from src.domain.diagrams.layout.routing.router import route_all
from src.domain.diagrams.layout.routing.scene import Connector, RoutedConnector, RoutingResult, RoutingScene
from src.domain.diagrams.layout.routing.visibility import Visibility
from src.domain.diagrams.layout.routing.widening import widened


def _extent(extent: Extent) -> dict[str, float]:
    return {"left": extent.left, "top": extent.top, "right": extent.right, "bottom": extent.bottom}


def _points(course: Sequence[Point]) -> list[list[float]]:
    return [[point.x, point.y] for point in course]


def _port(port: Port) -> dict[str, object]:
    return {"side": port.side.value, "at": port.at}


def scene_as_json(scene: RoutingScene) -> dict[str, object]:
    return {
        "elements": {key: _extent(extent) for key, extent in scene.elements.items()},
        "boxes": {key: _extent(extent) for key, extent in scene.boxes.items()},
        "text": {key: _extent(extent) for key, extent in scene.text.items()},
        "fixed_lines": [_points(line) for line in scene.fixed_lines],
    }


def connector_as_json(connector: Connector) -> dict[str, object]:
    written: dict[str, object] = {
        "key": connector.key, "source": connector.source, "target": connector.target,
        "decorated": list(connector.decorated),
    }
    if connector.source_port is not None:
        written["source_port"] = _port(connector.source_port)
    if connector.target_port is not None:
        written["target_port"] = _port(connector.target_port)
    return written


def routed_as_json(routes: Mapping[str, RoutedConnector]) -> dict[str, object]:
    return {
        key: {"source_port": _port(routed.source_port), "target_port": _port(routed.target_port),
              "course": _points(routed.course)}
        for key, routed in routes.items()
    }


def result_as_json(result: RoutingResult) -> dict[str, object]:
    return {
        "routes": routed_as_json(result.routes),
        "unroutable": list(result.unroutable),
        "unseparated": [list(pair) for pair in result.unseparated],
    }


def _box(left: float, top: float, width: float, height: float) -> Extent:
    return Extent(left, top, left + width, top + height)


def _case(name: str, scene: RoutingScene, connectors: Sequence[Connector]) -> dict[str, object]:
    return {
        "name": name, "scene": scene_as_json(scene),
        "connectors": [connector_as_json(connector) for connector in connectors],
        "result": result_as_json(route_all(scene, connectors)),
    }


def _channel_scene() -> tuple[RoutingScene, list[Connector]]:
    """Five elements on the left, five on the right, a wall between with one gap: nudging's work."""
    left = {f"l{index}": _box(0, index * 80, 100, 40) for index in range(5)}
    right = {f"r{index}": _box(500, index * 80 + 20, 100, 40) for index in range(5)}
    wall_top, wall_bottom = _box(250, -100, 40, 260), _box(250, 200, 40, 300)
    elements = {**left, **right, "wall-top": wall_top, "wall-bottom": wall_bottom}
    connectors = [Connector(f"c{index}", f"l{index}", f"r{4 - index}") for index in range(5)]
    return RoutingScene(elements=elements), connectors


def _nested_scene() -> tuple[RoutingScene, list[Connector]]:
    """A member deep in two boxes, an element outside, and a box between holding neither end."""
    elements = {"member": _box(60, 80, 100, 40), "outside": _box(600, 300, 100, 40), "inner": _box(320, 40, 80, 40)}
    boxes = {
        "outer": _box(20, 20, 260, 200), "middle": _box(40, 50, 180, 100),
        "between": _box(300, 20, 140, 120),
    }
    text = {"band:outer": Extent(100, 20, 200, 44), "band:between": Extent(330, 20, 410, 36)}
    connectors = [
        Connector("out", "member", "outside"),
        Connector("to-box", "outside", "between", decorated=(False, True)),
        Connector("whole", "outer", "member", decorated=(True, False)),
    ]
    return RoutingScene(elements=elements, boxes=boxes, text=text), connectors


def _walled_scene() -> tuple[RoutingScene, list[Connector]]:
    """An element ringed by four others so close no stub leaves it: unroutable, and said so."""
    elements = {
        "walled": _box(100, 100, 60, 30), "north": _box(90, 70, 80, 20), "south": _box(90, 140, 80, 20),
        "west": _box(60, 90, 30, 50), "east": _box(170, 90, 30, 50), "far": _box(500, 100, 60, 30),
    }
    return RoutingScene(elements=elements), [Connector("trapped", "walled", "far")]


def synthetic_scene(count: int, relations: int, seed: int = 1) -> tuple[RoutingScene, list[Connector]]:
    """*count* elements in a grid, slightly jittered, and *relations* connectors, most to neighbours."""
    chance = random.Random(seed)
    columns = int(count**0.5) + 1
    elements: dict[str, Extent] = {}
    for index in range(count):
        width, height = chance.choice(((120, 50), (160, 60), (140, 52), (20, 20)))
        left, top = (index % columns) * 260 + chance.randint(0, 40), (index // columns) * 180 + chance.randint(0, 40)
        elements[f"e{index}"] = Extent(left, top, left + width, top + height)
    keys = list(elements)
    connectors: list[Connector] = []
    for number in range(relations):
        first = chance.randrange(count)
        step = chance.choice((-1, 1, columns, -columns, columns + 1, 2, 2 * columns, chance.randrange(-count, count)))
        second = min(count - 1, max(0, first + step))
        if first != second:
            connectors.append(Connector(f"r{number}", keys[first], keys[second], (False, True)))
    return RoutingScene(elements=elements), connectors


def _end(value: float) -> float | None:
    """A segment's end, None where nothing stops it (JSON has no infinity)."""
    return None if math.isinf(value) else value


def graph_scene() -> tuple[RoutingScene, list[Point]]:
    """Three elements in a row, the middle one taller, one below it, a box round two of them and a
    title band: the segments through the short elements' corners stop at the tall one, and two
    terminals join the graph."""
    elements = {
        "a": _box(0, 0, 80, 40), "b": _box(160, -20, 80, 100), "c": _box(320, 0, 80, 40), "d": _box(160, 160, 80, 40),
    }
    boxes = {"group": _box(140, -50, 300, 150)}
    text = {"band:group": Extent(150, -50, 260, -30)}
    return RoutingScene(elements=elements, boxes=boxes, text=text), [Point(40, -30), Point(200, 220)]


def build_graph() -> dict[str, object]:
    scene, terminals = graph_scene()
    graph = Visibility(scene).graph
    joined = graph.joined(terminals)
    joins = sorted(
        [joined.x(node), joined.y(node), joined.x(other), joined.y(other)]
        for node in range(joined.size) for direction in (EAST, SOUTH)
        if (other := joined.next(node, direction)) >= 0
    )
    return {
        "scene": scene_as_json(scene), "terminals": _points(terminals),
        "level": [[at, _end(low), _end(high)] for at, low, high in graph.level.segments],
        "upright": [[at, _end(low), _end(high)] for at, low, high in graph.upright.segments],
        "joins": joins,
    }


def widening_scene() -> tuple[RoutingScene, list[Connector]]:
    """A box over two boxes side by side, all three in a fourth, 20 px apart, and lines between the
    upper box's elements and the lower ones' that must run along those gaps."""
    elements = {
        "a1": _box(40, 60, 100, 40), "a2": _box(240, 60, 100, 40), "a3": _box(500, 60, 100, 40),
        "a4": _box(720, 60, 100, 40), "b1": _box(40, 260, 100, 40), "b2": _box(260, 260, 100, 40),
        "c1": _box(480, 260, 100, 40), "c2": _box(720, 260, 100, 40),
    }
    boxes = {
        "whole": _box(0, 0, 900, 360), "upper": _box(20, 20, 860, 120),
        "left": _box(20, 160, 400, 180), "right": _box(440, 160, 440, 180),
    }
    text = {"band:whole": Extent(0, 0, 900, 16), "band:upper": Extent(20, 20, 880, 36)}
    pairs = (
        ("a1", "c2"), ("a2", "c1"), ("a4", "b1"), ("a3", "b2"), ("a1", "c1"), ("a4", "b2"), ("b1", "c2"), ("b2", "c1"),
    )
    connectors = [Connector(f"r{number}", source, target) for number, (source, target) in enumerate(pairs, 1)]
    return RoutingScene(elements=elements, boxes=boxes, text=text), connectors


def build_widening() -> dict[str, object]:
    scene, connectors = widening_scene()
    courses = [routed.course for routed in route_all(scene, connectors).routes.values()]
    return {
        "scene": scene_as_json(scene), "connectors": [connector_as_json(connector) for connector in connectors],
        "channels": [
            {"low": channel.low, "high": channel.high, "across": channel.across, "start": channel.start,
             "end": channel.end, "first": channel.first, "last": channel.last, "lines": channel.lines,
             "run": channel.run, "wider_by": channel.wider_by}
            for channel in channels(scene.boxes, [*scene.elements.values(), *scene.text.values()], courses)
        ],
        "widened": scene_as_json(widened(scene, connectors)),
    }


def inside_scene(*, room_below: bool = True) -> tuple[RoutingScene, list[Connector]]:
    """Two members near the top of their box with a third between them: over the top, outside the box,
    is the short way; under the third, inside, is the way the bounds allow — where there is room."""
    middle = _box(250, 10, 100, 150) if room_below else _box(250, 10, 100, 185)
    elements = {"a": _box(40, 30, 100, 40), "b": _box(460, 30, 100, 40), "c": middle}
    return RoutingScene(elements=elements, boxes={"g": _box(0, 0, 600, 200)}), [Connector("ab", "a", "b")]


def heavy_edit() -> tuple[RoutingScene, RoutingScene, list[Connector], frozenset[str]]:
    """Before and after a drag that moves two elements: one onto the stub of a port stated at 0.75 of
    its side, so that connector has no route, and one across the route of a connector neither of whose
    ends moved. The quick pass must answer what the full pass answers about both."""
    before = {
        "a": _box(100, 100, 100, 60), "b": _box(400, 100, 100, 60),
        "c": _box(100, 300, 100, 40), "d": _box(400, 300, 100, 40),
        "w": _box(-200, 400, 40, 14), "e": _box(-200, 500, 60, 40),
    }
    after = {**before, "w": _box(50, 138, 40, 14), "e": _box(270, 280, 60, 80)}
    connectors = [
        Connector("ab", "a", "b", source_port=Port(Side.LEFT, 0.75)),
        Connector("cd", "c", "d"),
    ]
    return RoutingScene(elements=before), RoutingScene(elements=after), connectors, frozenset({"w", "e"})


def _quick_case(before: RoutingScene, after: RoutingScene, connectors: Sequence[Connector],
                changed: frozenset[str]) -> dict[str, object]:
    previous = route_all(before, connectors)
    quick = route_all(after, connectors, previous=previous.routes, changed=changed)
    return {
        "scene": scene_as_json(after), "connectors": [connector_as_json(one) for one in connectors],
        "previous": routed_as_json(previous.routes), "changed": sorted(changed), "result": result_as_json(quick),
        "full": result_as_json(route_all(after, connectors)),
    }


def build_routing() -> dict[str, object]:
    a, b, c = _box(0, 100, 100, 60), _box(400, 100, 100, 60), _box(220, 60, 60, 140)
    cases = [
        _case("facing elements in line run straight", RoutingScene(elements={"a": a, "b": b}),
              [Connector("ab", "a", "b")]),
        _case("an element in the way is gone round", RoutingScene(elements={"a": a, "b": b, "c": c}),
              [Connector("ab", "a", "b")]),
        _case("a title band in the way is gone round",
              RoutingScene(elements={"a": a, "b": _box(400, 300, 100, 60)}, text={"band": Extent(150, 60, 350, 400)}),
              [Connector("ab", "a", "b")]),
        _case("a stated port is kept", RoutingScene(elements={"a": a, "b": b, "c": c}),
              [Connector("ab", "a", "b", source_port=Port(Side.BOTTOM, 0.25))]),
        _case("an element to itself loops round its corner", RoutingScene(elements={"a": a}),
              [Connector("aa", "a", "a")]),
        _case("two elements closer than a stub are joined the most direct way",
              RoutingScene(elements={"a": a, "b": _box(0, 168, 100, 40)}), [Connector("ab", "a", "b")]),
        _case("into and out of nested boxes, round a box that holds neither end", *_nested_scene()),
        _case("many routes through one channel are nudged apart", *_channel_scene()),
        _case("a walled-in element is unroutable", *_walled_scene()),
        _case("two members of a box are joined inside it", *inside_scene()),
        _case("and outside it only where no way inside exists", *inside_scene(room_below=False)),
        _case("a synthetic arrangement of forty elements", *synthetic_scene(40, 60, seed=3)),
    ]
    scene, connectors = _channel_scene()
    previous = route_all(scene, connectors)
    moved = dict(scene.elements)
    moved["l2"] = _box(0, 150, 100, 40)
    moved_scene = RoutingScene(elements=moved)
    quick = route_all(moved_scene, connectors, previous=previous.routes, changed=frozenset({"l2"}))
    return {
        "graph": build_graph(),
        "widening": build_widening(),
        "cases": cases,
        "quick": {
            "scene": scene_as_json(moved_scene), "connectors": [connector_as_json(one) for one in connectors],
            "previous": routed_as_json(previous.routes), "changed": ["l2"], "result": result_as_json(quick),
        },
        "heavy_edit": _quick_case(*heavy_edit()),
    }
