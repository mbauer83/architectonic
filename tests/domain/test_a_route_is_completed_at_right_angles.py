"""The course a stated route runs, and the fixtures that hold the two implementations of it together.

`tests/fixtures/layout_geometry/` is what the TypeScript mirror is tested against. The first test
here holds every file to what the Python domain answers for its cases, so the files cannot go stale
and neither side can move alone. The rest state the rule itself in a few cases written out by hand —
a fixture that only ever agreed with its generator would pass against any rule at all.
"""

from __future__ import annotations

import json
import random

import pytest

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import Port, Route, Side
from src.domain.diagrams.layout.orthogonal import (
    IN_LINE,
    completed_course,
    course_of,
    fraction_along,
    half_up,
    point_along,
    stated_course,
)
from tests.support.layout_geometry_fixtures import BUILDERS, FIXTURES, WALK_MOVES, as_text

_A = Extent(0, 0, 100, 60)
_B = Extent(300, 200, 420, 260)


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_each_shared_fixture_is_what_the_python_domain_answers(name: str) -> None:
    stored = (FIXTURES / name).read_text(encoding="utf-8")

    assert stored == as_text(BUILDERS[name]()), (
        f"{name} is not what the layout domain computes for its cases. If the rule changed on purpose, "
        "run `uv run python -m tests.support.layout_geometry_fixtures` and make the same change in "
        "tools/gui/src/domain/layout, which is tested against these files."
    )


def test_the_walk_is_as_long_as_the_plan_asks_and_exercises_every_outcome() -> None:
    """A truncated file would agree with a truncated builder, and a walk in which nothing happens proves nothing."""
    walk = json.loads((FIXTURES / "walk.json").read_text(encoding="utf-8"))

    assert len(walk["steps"]) == WALK_MOVES >= 400  # noqa: PLR2004 — the plan's own number
    assert sum(1 for step in walk["steps"] if step["routes"]) > WALK_MOVES / 4
    assert any(step["rerouted"] for step in walk["steps"])
    assert any(step["conflicts"] for step in walk["steps"])


class TestCompletion:
    def test_facing_ports_out_of_line_are_joined_by_a_z_through_the_middle(self) -> None:
        course = course_of(Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5)), _A, _B)

        assert course == (Point(100, 30), Point(200, 30), Point(200, 230), Point(300, 230))

    def test_ports_on_sides_at_right_angles_are_joined_by_an_l(self) -> None:
        course = course_of(Route(Port(Side.RIGHT, 0.5), Port(Side.TOP, 0.5)), _A, _B)

        assert course == (Point(100, 30), Point(360, 30), Point(360, 200))

    def test_a_bottom_port_leaves_downwards_when_no_bend_says_where_to(self) -> None:
        """The spike drew this first run sideways: it guessed the direction from the previous point."""
        course = course_of(Route(Port(Side.BOTTOM, 0.5), Port(Side.TOP, 0.5)), _A, _B)

        assert course is not None
        assert course[1] == Point(50, 130)

    def test_a_spur_is_kept_because_it_is_what_was_stated(self) -> None:
        back = Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((160, 30), (160, 100), (50, 100), (50, 10)))

        assert Point(50, 10) in stated_course(back, _A, _B)

    def test_a_route_leaving_a_port_to_the_router_has_no_whole_course(self) -> None:
        assert course_of(Route(Port(Side.RIGHT, 0.5)), _A, _B) is None

    def test_every_segment_of_a_completed_course_is_level_or_upright(self) -> None:
        chance = random.Random(11)
        sides = tuple(Side)
        for _ in range(500):
            bends = [
                Point(chance.randrange(-400, 800), chance.randrange(-400, 800)) for _ in range(chance.randrange(4))
            ]
            start, end = Point(chance.random() * 400, chance.random() * 400), Point(chance.random() * 400, 400.5)
            course = completed_course(start, chance.choice(sides), bends, end, chance.choice(sides))

            assert all(
                abs(a.x - b.x) <= IN_LINE or abs(a.y - b.y) <= IN_LINE
                for a, b in zip(course, course[1:], strict=False)
            ), course
            assert (course[0], course[-1]) == (start, end)


class TestAlongACourse:
    _COURSE = (Point(0, 0), Point(100, 0), Point(100, 100))

    def test_a_fraction_names_a_point_and_the_point_gives_the_fraction_back(self) -> None:
        for at in (0.0, 0.2, 0.5, 0.75, 1.0):
            assert fraction_along(self._COURSE, point_along(self._COURSE, at)) == pytest.approx(at)

    def test_a_point_off_the_course_is_measured_at_the_place_nearest_it(self) -> None:
        assert fraction_along(self._COURSE, Point(50, -30)) == pytest.approx(0.25)


def test_a_half_rounds_up_as_it_does_in_the_browser() -> None:
    """Python's own `round` sends 0.5 and 2.5 to the even neighbour; JavaScript's sends both up."""
    assert [half_up(value) for value in (0.5, 1.5, 2.5, -0.5, -1.5, 2.4999)] == [1, 2, 3, 0, -1, 2]
