"""The router keeps the hard readability rules, and the soft ones where the hard ones leave room.

Each test builds the smallest arrangement where the rule decides something, and states it through
the same predicates the verifier and the TypeScript mirror apply (`route_quality`, `text_clearance`).
"""

from __future__ import annotations

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Route, Side
from src.domain.diagrams.layout.orthogonal import course_of, port_point
from src.domain.diagrams.layout.route_quality import END_RUN, bends_at_ends, runs_along
from src.domain.diagrams.layout.text_clearance import texts_crossed
from src.infrastructure.rendering.layout.relation_routing import RelationRouting, Undecided
from src.infrastructure.rendering.layout.router import Surroundings

_A = Extent(0, 100, 100, 160)
_B = Extent(400, 100, 500, 160)


def _course(routes: dict[str, Route], key: str, extents: dict[str, Extent], ends: tuple[str, str]) -> tuple[Point, ...]:
    course = course_of(routes[key], extents[ends[0]], extents[ends[1]])
    assert course is not None
    return course


def test_a_route_goes_round_text_rather_than_through_it() -> None:
    band = Extent(150, 80, 350, 180)
    extents = {"a": _A, "b": _B}
    routing = RelationRouting(extents, extents, Surroundings(text={"band": band}))
    routes = routing.decide([Undecided("r", "a", "b")])

    assert texts_crossed(_course(routes, "r", extents, ("a", "b")), {"band": band}) == ()


def test_a_route_never_runs_along_a_box_border() -> None:
    box = Extent(-40, 127, 540, 400)  # its top edge lies on the straight line between the two
    extents = {"a": _A, "b": _B}
    routing = RelationRouting(extents, extents, Surroundings(borders=[box]))
    routes = routing.decide([Undecided("r", "a", "b")])

    assert runs_along(_course(routes, "r", extents, ("a", "b")), (), [box]) == ()


def test_where_a_route_bends_it_reaches_a_decorated_end_by_a_straight_run() -> None:
    target = Extent(400, 300, 500, 360)
    extents = {"a": _A, "b": target}
    routes = RelationRouting(extents, extents).decide([Undecided("r", "a", "b", decorated=(False, True))])
    course = _course(routes, "r", extents, ("a", "b"))

    assert len(course) > 2  # noqa: PLR2004 — the two are not in line, so it bends
    assert bends_at_ends(course, (False, True)) == ()
    assert course[-1].distance_to(course[-2]) >= END_RUN - 0.5


def test_ends_sharing_one_side_never_arrive_at_one_point() -> None:
    box = Extent(400, 0, 700, 300)
    extents = {"box": box, "a": Extent(0, 0, 100, 50), "b": Extent(0, 125, 100, 175), "c": Extent(0, 250, 100, 300)}
    routes = RelationRouting(extents, {key: extent for key, extent in extents.items() if key != "box"}).decide(
        [Undecided(name, name, "box") for name in ("a", "b", "c")]
    )
    arrivals = {port_point(box, route.target) for route in routes.values() if route.target is not None}

    assert len(arrivals) == 3  # noqa: PLR2004 — three relations, three points


def test_an_end_at_a_box_attaches_below_its_title_band_on_a_side() -> None:
    box = Extent(400, 0, 700, 300)
    band = Extent(400, 0, 700, 40)
    extents = {"box": box, "a": Extent(0, 0, 100, 40)}
    routing = RelationRouting(extents, {"a": extents["a"]}, Surroundings(text={"band": band}), bands={"box": band})
    route = routing.decide([Undecided("r", "a", "box")])["r"]

    assert route.target is not None
    assert port_point(box, route.target).y > band.bottom


def test_two_elements_closer_than_a_stub_are_joined_the_most_direct_way() -> None:
    """Not a loop round one of them: no route keeps I1 between them, so the shortest bend is taken."""
    extents = {"a": Extent(0, 0, 100, 40), "b": Extent(0, 48, 100, 88)}
    route = RelationRouting(extents, extents).decide([Undecided("r", "a", "b")])["r"]
    course = _course({"r": route}, "r", extents, ("a", "b"))

    assert len(course) <= 3  # noqa: PLR2004 — straight, or one bend


def test_a_box_and_an_element_inside_it_are_joined_by_one_straight_run_through_nothing_else() -> None:
    whole, part, other = Extent(0, 0, 400, 300), Extent(150, 100, 250, 150), Extent(150, 200, 250, 250)
    extents = {"whole": whole, "part": part, "other": other}
    route = RelationRouting(extents, {"part": part, "other": other}).decide([Undecided("r", "whole", "part")])["r"]
    course = _course({"r": route}, "r", extents, ("whole", "part"))

    assert len(course) == 2  # noqa: PLR2004 — one run
    assert not other.shrunk_by(1.0).is_entered_by(course[0], course[1])  # type: ignore[union-attr]


def test_a_route_does_not_enter_a_box_that_holds_neither_of_its_ends() -> None:
    walled = Extent(150, 60, 350, 200)
    extents = {"a": _A, "b": _B, "walled": walled}
    route = RelationRouting(extents, {"a": _A, "b": _B}).decide([Undecided("r", "a", "b")])["r"]
    course = _course({"r": route}, "r", extents, ("a", "b"))
    inside = walled.shrunk_by(1.0)

    assert inside is not None
    assert not any(inside.is_entered_by(start, end) for start, end in zip(course, course[1:], strict=False))


def test_a_port_given_its_side_keeps_it() -> None:
    extents = {"a": _A, "b": _B}
    stated = Route(source=Port(Side.BOTTOM, 0.25))
    route = RelationRouting(extents, extents).decide([Undecided("r", "a", "b", stated)])["r"]

    assert route.source == Port(Side.BOTTOM, 0.25)
