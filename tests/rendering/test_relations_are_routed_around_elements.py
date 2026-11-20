"""The router: a relation goes round the elements it does not join, and what a move breaks is put right.

The property the plan asks for is at the bottom: four hundred random moves of one element at a time,
on several arrangements, after each of which every arrow still satisfies I1 and I2 unless its two
elements overlap or touch — the one conflict no route satisfies. Zero failures, not few.
"""

from __future__ import annotations

import random

import pytest

from src.domain.diagrams.layout.attachment import breaches_of, elements_crossed, ends_conflict, keep_attached
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import LabelAnchor, Port, Route, Side
from src.domain.diagrams.layout.orthogonal import STUB, course_of
from src.infrastructure.rendering.layout.label_placement import label_box, placed_label
from src.infrastructure.rendering.layout.relation_routing import RelationRouting, Undecided
from src.infrastructure.rendering.layout.router import Router
from tests.support.layout_geometry_fixtures import WALK_MOVES, walk_scene

_A = Extent(0, 0, 100, 60)
_B = Extent(400, 0, 500, 60)
_WALL = Extent(200, -100, 260, 160)


def _is_upright_or_level(course: tuple[Point, ...]) -> bool:
    return all(a.x == b.x or a.y == b.y for a, b in zip(course, course[1:], strict=False))


class TestOneRoute:
    def test_two_facing_ports_with_nothing_between_are_joined_without_a_detour(self) -> None:
        found = Router({"a": _A, "b": _B}).route(_A, Port(Side.RIGHT, 0.5), _B, Port(Side.LEFT, 0.5))

        assert found is not None
        assert found.course == (Point(100, 30), Point(400, 30))

    def test_an_element_in_the_way_is_gone_round_at_the_margin(self) -> None:
        extents = {"a": _A, "b": _B, "wall": _WALL}
        found = Router(extents).route(_A, Port(Side.RIGHT, 0.5), _B, Port(Side.LEFT, 0.5))

        assert found is not None
        assert _is_upright_or_level(found.course)
        assert elements_crossed(found.course, extents, ("a", "b")) == ()
        assert all(_WALL.distance_to(point) >= STUB for point in found.bends)

    def test_it_leaves_and_arrives_by_a_stub(self) -> None:
        extents = {"a": _A, "b": _B, "wall": _WALL}
        routing = RelationRouting(extents, extents)
        route = routing.rerouted(Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5)), "a", "b")

        assert route is not None
        assert route.via
        assert breaches_of(route, _A, _B) == ()

    def test_a_port_with_an_element_standing_within_a_stub_of_it_has_no_way_out(self) -> None:
        hard_by = Extent(105, 0, 180, 60)

        router = Router({"a": _A, "b": _B, "c": hard_by})

        assert router.route(_A, Port(Side.RIGHT, 0.5), _B, Port(Side.LEFT, 0.5)) is None

    def test_an_element_an_end_is_drawn_inside_may_be_crossed(self) -> None:
        whole = Extent(-40, -40, 240, 120)
        extents = {"a": _A, "b": _B, "whole": whole}
        route = RelationRouting(extents, {"a": _A, "b": _B, "whole": whole}).rerouted(
            Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5)), "a", "b"
        )

        assert route is not None
        assert route.via == ()


class TestDecidingWhatALayoutLeavesOpen:
    def test_ends_sharing_a_side_are_spread_along_it_in_the_order_of_what_they_lead_to(self) -> None:
        hub, up_there, down_there = Extent(0, 100, 100, 200), Extent(400, 100, 500, 140), Extent(400, 160, 500, 200)
        extents = {"hub": hub, "up": up_there, "down": down_there}
        routes = RelationRouting(extents, extents).decide(
            [Undecided("to-down", "hub", "down"), Undecided("to-up", "hub", "up")]
        )
        up, down = routes["to-up"].source, routes["to-down"].source

        assert up is not None
        assert down is not None
        assert (up.side, down.side) == (Side.RIGHT, Side.RIGHT)
        assert up.at < down.at

    def test_a_stated_port_is_kept_and_only_the_other_end_decided(self) -> None:
        extents = {"a": _A, "b": _B}
        stated = Route(source=Port(Side.BOTTOM, 0.25))
        decided = RelationRouting(extents, extents).decide([Undecided("r", "a", "b", stated)])["r"]

        assert decided.source == Port(Side.BOTTOM, 0.25)
        assert decided.target is not None
        assert breaches_of(decided, _A, _B) == ()

    def test_a_relation_from_an_element_to_itself_loops_outside_it(self) -> None:
        extents = {"a": _A}
        loop = RelationRouting(extents, extents).decide([Undecided("r", "a", "a")])["r"]
        course = course_of(loop, _A, _A)

        assert course is not None
        assert breaches_of(loop, _A, _A) == ()

    def test_every_decided_route_on_a_real_arrangement_is_sound_and_crosses_nothing(self) -> None:
        extents, ends = walk_scene()
        routes = RelationRouting(extents, extents).decide(
            [Undecided(key, source, target) for key, (source, target) in ends.items()]
        )

        for key, route in routes.items():
            source, target = (extents[end] for end in ends[key])
            course = course_of(route, source, target)
            assert course is not None
            assert breaches_of(route, source, target) == (), key
            assert elements_crossed(course, extents, ends[key]) == (), key


class TestWhereALabelSits:
    _COURSE = (Point(100, 30), Point(200, 30), Point(200, 230), Point(300, 230))
    _SIZE = (60.0, 14.0)

    def test_a_label_nobody_placed_sits_beside_the_middle_of_its_route(self) -> None:
        anchor = placed_label(self._COURSE, self._SIZE, [])
        box = label_box(self._COURSE, anchor, self._SIZE)

        assert anchor.at == 0.5  # noqa: PLR2004 — the middle
        assert box.left > 200  # noqa: PLR2004 — right of the upright run it labels, not over it

    def test_it_moves_along_or_across_the_route_to_stay_clear_of_an_element(self) -> None:
        in_the_way = Extent(190, 100, 320, 160)
        anchor = placed_label(self._COURSE, self._SIZE, [in_the_way])

        assert label_box(self._COURSE, anchor, self._SIZE).overlap_with(in_the_way) is None

    def test_two_labels_on_one_route_do_not_sit_on_each_other(self) -> None:
        first = label_box(self._COURSE, placed_label(self._COURSE, self._SIZE, []), self._SIZE)
        second = label_box(self._COURSE, placed_label(self._COURSE, self._SIZE, [first]), self._SIZE)

        assert first.overlap_with(second) is None

    def test_an_anchor_rides_with_the_route_when_the_route_changes(self) -> None:
        anchor = LabelAnchor(0.5, 10, 0)
        moved = tuple(Point(point.x + 50, point.y) for point in self._COURSE)

        assert label_box(moved, anchor, self._SIZE).left == label_box(self._COURSE, anchor, self._SIZE).left + 50


@pytest.mark.parametrize("seed", [7, 11, 20261111])
def test_four_hundred_random_moves_leave_no_arrow_detached(seed: int) -> None:
    """I1–I5 after every move: zero failures. What remains is counted, and is only ever a conflict."""
    extents, ends = walk_scene()
    routes = RelationRouting(extents, extents).decide(
        [Undecided(key, source, target) for key, (source, target) in ends.items()]
    )
    chance = random.Random(seed)
    failures: list[tuple[int, str, tuple[str, ...]]] = []
    turned_or_reformed = rerouted = 0

    for step in range(WALK_MOVES):
        moved = chance.choice(sorted(extents))
        before = extents[moved]
        left, top = before.left + chance.randrange(-300, 301), before.top + chance.randrange(-200, 201)
        extents[moved] = Extent(left, top, left + before.width, top + before.height)

        kept = keep_attached(routes, ends=ends, extents=extents, changed=[moved])
        turned_or_reformed += sum(
            1 for key, route in kept.routes.items()
            if (route.source, route.target) != (routes[key].source, routes[key].target)
        )
        routes = dict(kept.routes)
        routing = RelationRouting(extents, extents)
        for key in kept.crossing:
            again = routing.rerouted(routes[key], *ends[key])
            if again is not None:
                routes[key] = again
                rerouted += 1

        for key, route in routes.items():
            source, target = (extents[end] for end in ends[key])
            broken = breaches_of(route, source, target)
            if broken and not ends_conflict(source, target):
                failures.append((step, key, tuple(breach.value for breach in broken)))

    assert failures == []
    # The walk must have had something to repair, or it proved nothing.
    assert turned_or_reformed > WALK_MOVES / 10
    assert rerouted > 0
