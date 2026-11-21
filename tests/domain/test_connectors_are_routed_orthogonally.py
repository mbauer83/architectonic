"""The router (GD 2009: a visibility graph, A* per connector, nudging) and the rules built into it.

Each rule is stated where it decides something, through the predicates the verifier and the
TypeScript mirror apply. The routes themselves, to the pixel, are the shared fixtures' business
(`test_a_route_is_completed_at_right_angles` holds the file to this router; vitest holds the
TypeScript router to the file).
"""

from __future__ import annotations

import math
import random
import time

import pytest

from src.domain.diagrams.layout.attachment import breaches_of, elements_crossed, ends_conflict, keep_attached
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Side
from src.domain.diagrams.layout.orthogonal import course_of
from src.domain.diagrams.layout.route_quality import END_RUN, bends_at_ends, runs_along
from src.domain.diagrams.layout.routing.graph import EAST, NORTH, SOUTH, WEST
from src.domain.diagrams.layout.routing.router import as_route, rerouted, route_all
from src.domain.diagrams.layout.routing.scene import Connector, RoutingScene
from src.domain.diagrams.layout.routing.search import REVERSE
from src.domain.diagrams.layout.routing.visibility import Visibility
from src.domain.diagrams.layout.text_clearance import texts_crossed
from tests.support.layout_geometry_fixtures import WALK_MOVES, walk_scene
from tests.support.routing_fixtures import graph_scene, synthetic_scene

_A, _B = Extent(0, 100, 100, 160), Extent(400, 100, 500, 160)


def _only(scene: RoutingScene, *connectors: Connector) -> tuple[Point, ...]:
    result = route_all(scene, connectors)
    assert result.unroutable == ()
    return result.routes[connectors[0].key].course


def test_a_segment_of_visibility_stops_at_the_first_element_in_its_way() -> None:
    """The graph is the paper's, not a grid of every line: a line through the short element's top
    stops at the tall one beside it, so it meets no line on the tall one's far side."""
    scene, _terminals = graph_scene()
    graph = Visibility(scene).graph
    tall = Visibility(scene).grown["b"]

    on_short_top = [(low, high) for at, low, high in graph.level.segments if at == -8]
    assert on_short_top == [(-math.inf, tall.left), (tall.right, math.inf)]
    for x, y in zip(graph.xs, graph.ys, strict=True):
        assert not any(rect.left < x < rect.right and rect.top < y < rect.bottom for rect in graph.obstacles)


def test_a_search_s_terminals_are_joined_to_the_graph_and_the_scene_s_graph_is_left_as_it_was() -> None:
    scene, terminals = graph_scene()
    graph = Visibility(scene).graph
    before = list(graph.next)

    joined = graph.joined(terminals)

    assert graph.next == before
    for terminal in terminals:
        node = joined.node_at(terminal)
        assert any(joined.next(node, direction) >= 0 for direction in (EAST, WEST, SOUTH, NORTH))
        for direction in (EAST, WEST, SOUTH, NORTH):
            if (other := joined.next(node, direction)) >= 0:
                assert joined.next(other, REVERSE[direction]) == node


def test_facing_elements_in_line_are_joined_by_one_straight_run() -> None:
    course = _only(RoutingScene(elements={"a": _A, "b": _B}), Connector("ab", "a", "b"))

    assert course == (Point(100, 130), Point(400, 130))


def test_an_element_in_the_way_is_gone_round() -> None:
    elements = {"a": _A, "b": _B, "c": Extent(220, 60, 280, 200)}
    course = _only(RoutingScene(elements=elements), Connector("ab", "a", "b"))

    assert elements_crossed(course, elements, ("a", "b")) == ()


def test_text_is_an_obstacle() -> None:
    band = Extent(150, 60, 350, 400)
    scene = RoutingScene(elements={"a": _A, "b": Extent(400, 300, 500, 360)}, text={"band": band})
    course = _only(scene, Connector("ab", "a", "b"))

    assert texts_crossed(course, {"band": band}) == ()


def test_a_decorated_end_is_reached_by_a_straight_run_and_an_undecorated_one_by_a_stub() -> None:
    scene = RoutingScene(elements={"a": _A, "b": Extent(400, 300, 500, 360)})
    course = _only(scene, Connector("ab", "a", "b", decorated=(False, True)))

    assert len(course) > 2  # noqa: PLR2004 — not in line, so it bends
    assert bends_at_ends(course, (False, True)) == ()
    assert course[-1].distance_to(course[-2]) >= END_RUN


def test_a_route_to_a_member_crosses_its_boxes_at_right_angles_and_never_enters_a_box_holding_neither_end() -> None:
    member, outside = Extent(60, 80, 160, 120), Extent(600, 300, 700, 340)
    outer, between = Extent(20, 20, 280, 220), Extent(300, 200, 440, 500)
    scene = RoutingScene(elements={"member": member, "outside": outside}, boxes={"outer": outer, "between": between})
    course = _only(scene, Connector("out", "member", "outside"))
    inside = between.shrunk_by(1.0)

    assert inside is not None
    assert not any(inside.is_entered_by(a, b) for a, b in zip(course, course[1:], strict=False))
    assert runs_along(course, (), [outer, between]) == ()


def test_a_box_and_its_part_are_joined_by_one_run_from_the_part_to_the_box_s_border() -> None:
    whole, part = Extent(0, 0, 400, 300), Extent(150, 100, 250, 150)
    scene = RoutingScene(elements={"part": part}, boxes={"whole": whole})

    assert len(_only(scene, Connector("w", "whole", "part"))) == 2  # noqa: PLR2004 — one run


def test_ends_sharing_a_side_are_spread_along_it() -> None:
    box = Extent(400, 0, 700, 300)
    elements = {"a": Extent(0, 0, 100, 50), "b": Extent(0, 125, 100, 175), "c": Extent(0, 250, 100, 300)}
    result = route_all(RoutingScene(elements=elements, boxes={"box": box}), [
        Connector(name, name, "box") for name in elements
    ])

    assert len({routed.course[-1] for routed in result.routes.values()}) == 3  # noqa: PLR2004


def test_a_stated_port_is_kept() -> None:
    elements = {"a": _A, "b": _B, "c": Extent(220, 60, 280, 200)}
    stated = Connector("ab", "a", "b", source_port=Port(Side.BOTTOM, 0.25))
    routed = route_all(RoutingScene(elements=elements), [stated])

    assert routed.routes["ab"].source_port == Port(Side.BOTTOM, 0.25)


def test_a_connector_no_route_reaches_is_reported_and_not_drawn() -> None:
    elements = {
        "walled": Extent(100, 100, 160, 130), "north": Extent(90, 70, 170, 90), "south": Extent(90, 140, 170, 160),
        "west": Extent(60, 90, 90, 140), "east": Extent(170, 90, 200, 140), "far": Extent(500, 100, 560, 130),
    }
    result = route_all(RoutingScene(elements=elements), [Connector("trapped", "walled", "far")])

    assert result.unroutable == ("trapped",)
    assert "trapped" not in result.routes


def test_every_route_of_an_arrangement_keeps_the_hard_rules_unless_reported() -> None:
    """Traceable end to end: no element or text crossed, no bend at a decorated end, no run along
    another route or a border — except between connectors nudging reports it could not separate."""
    scene, connectors = synthetic_scene(40, 60, seed=3)
    result = route_all(scene, connectors)
    reported = {key for pair in result.unseparated for key in pair}
    by_key = {connector.key: connector for connector in connectors}

    for key, routed in result.routes.items():
        connector = by_key[key]
        assert elements_crossed(routed.course, scene.elements, (connector.source, connector.target)) == (), key
        assert bends_at_ends(routed.course, connector.decorated) == (), key
        if key not in reported:
            others = [other.course for other_key, other in result.routes.items() if other_key != key]
            assert runs_along(routed.course, others) == (), key


@pytest.mark.parametrize("seed", [7, 11, 20261111])
def test_four_hundred_random_moves_leave_no_arrow_detached(seed: int) -> None:
    """I1 and I2 after every move, with the router finding again what a move made cross (I5)."""
    extents, ends = walk_scene()
    first = route_all(RoutingScene(elements=extents), [Connector(key, *pair) for key, pair in ends.items()])
    routes = {key: as_route(routed) for key, routed in first.routes.items()}
    chance = random.Random(seed)
    failures: list[tuple[int, str]] = []
    for step in range(WALK_MOVES):
        moved = chance.choice(sorted(extents))
        before = extents[moved]
        left, top = before.left + chance.randrange(-300, 301), before.top + chance.randrange(-200, 201)
        extents[moved] = Extent(left, top, left + before.width, top + before.height)
        kept = keep_attached(routes, ends=ends, extents=extents, changed=[moved])
        routes = dict(kept.routes)
        for key in kept.crossing:
            again = rerouted(RoutingScene(elements=extents), Connector(
                key, *ends[key], source_port=routes[key].source, target_port=routes[key].target,
            ))
            if again is not None:
                routes[key] = again
        for key, route in routes.items():
            source, target = (extents[end] for end in ends[key])
            if breaches_of(route, source, target) and not ends_conflict(source, target):
                failures.append((step, key))
    assert failures == []


def test_a_drag_s_quick_pass_routes_only_what_moved() -> None:
    scene, connectors = synthetic_scene(40, 60, seed=3)
    full = route_all(scene, connectors)
    moved = dict(scene.elements)
    shifted = moved["e5"]
    moved["e5"] = Extent(shifted.left + 30, shifted.top, shifted.right + 30, shifted.bottom)
    quick = route_all(RoutingScene(elements=moved), connectors, previous=full.routes, changed=frozenset({"e5"}))
    touched = {connector.key for connector in connectors if "e5" in (connector.source, connector.target)}

    for key, routed in quick.routes.items():
        if key not in touched:
            assert routed.course == full.routes[key].course, key


@pytest.mark.parametrize(("count", "relations", "budget"), [(60, 100, 30.0)])
def test_a_full_pass_over_a_large_view_finishes(count: int, relations: int, budget: float) -> None:
    """A guard against a router that stops finishing, not the drag budget: that is measured, not asserted."""
    scene, connectors = synthetic_scene(count, relations)
    started = time.perf_counter()
    route_all(scene, connectors)

    assert time.perf_counter() - started < budget


def test_course_of_the_route_form_matches_the_course_drawn() -> None:
    scene, connectors = synthetic_scene(12, 16, seed=5)
    result = route_all(scene, connectors)
    by_key = {connector.key: connector for connector in connectors}
    for key, routed in result.routes.items():
        connector = by_key[key]
        recompleted = course_of(as_route(routed), scene.extent_of(connector.source), scene.extent_of(connector.target))
        assert recompleted is not None
        assert len(recompleted) == len(routed.course), key
