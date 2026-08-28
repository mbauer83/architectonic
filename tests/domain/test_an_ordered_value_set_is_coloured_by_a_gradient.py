"""How a value set with an order becomes colours, and what the unset member takes.

Two constraints decide every number in `ATTRIBUTE_GRADIENTS`, and both are stated here because a
future edit to the stops is exactly where they get lost:

* **the unset member is white, and nothing else is neutral.** White means "not assessed"; a grey or
  near-white stop in the middle of a scale says the same thing in the same picture, and a reader
  cannot then tell an unassessed element from a middling one;
* **no stop is muddy.** Red interpolated straight to green runs through brown, because the two
  channels cross over at the middle — which is the half of the scale a reader most needs to read.
"""

from __future__ import annotations

import pytest

from src.domain.hex_colors import mix_colors
from src.domain.viewpoints.viewpoint_style_values import (
    ATTRIBUTE_GRADIENTS,
    DEFAULT_ATTRIBUTE_GRADIENT,
    UNSET_MEMBER_COLOR,
    color_along_stops,
    graded_colors,
)

MATURITY = ("Not Assessed", "Initial", "Developing", "Defined", "Managed", "Optimising")


def _channels(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _is_neutral(color: str, *, spread: int = 24) -> bool:
    """Grey or near-grey: the three channels close together, which is what reads as unset."""
    red, green, blue = _channels(color)
    return max(red, green, blue) - min(red, green, blue) <= spread


class TestTheUnsetMember:
    def test_it_is_white_whatever_the_gradient(self) -> None:
        for gradient in ATTRIBUTE_GRADIENTS:
            colours = dict(graded_colors(MATURITY, unset="Not Assessed", gradient=gradient))
            assert colours["Not Assessed"] == UNSET_MEMBER_COLOR, gradient

    def test_it_is_taken_out_of_the_spread_so_the_rest_use_the_whole_range(self) -> None:
        """Five graded members span the gradient end to end; they are not squeezed into four fifths
        of it because a sixth member exists that takes no place on the scale."""
        stops = ATTRIBUTE_GRADIENTS[DEFAULT_ATTRIBUTE_GRADIENT]
        colours = dict(graded_colors(MATURITY, unset="Not Assessed"))

        assert colours["Initial"] == color_along_stops(stops, 0.0)
        assert colours["Optimising"] == color_along_stops(stops, 1.0)

    def test_a_set_with_no_unset_member_grades_all_of_them(self) -> None:
        colours = dict(graded_colors(("low", "mid", "high")))

        assert UNSET_MEMBER_COLOR not in colours.values()
        assert len(set(colours.values())) == 3

    def test_a_single_graded_member_takes_the_far_end(self) -> None:
        """There is no position to interpolate to, and the far end is the one that reads as arrived."""
        stops = ATTRIBUTE_GRADIENTS[DEFAULT_ATTRIBUTE_GRADIENT]

        colours = dict(graded_colors(("Not Assessed", "Done"), unset="Not Assessed"))

        assert colours["Done"] == color_along_stops(stops, 1.0)


class TestNoGradientReachesNeutral:
    """The constraint that ruled out the standard colour-blind-safe schemes, which are diverging and
    pivot on a neutral. Asserted over every member of every gradient, not over the declared stops
    alone: a stop can be colourful while the point between two of them is not."""

    @pytest.mark.parametrize("gradient", sorted(ATTRIBUTE_GRADIENTS))
    def test_no_graded_member_reads_as_grey(self, gradient: str) -> None:
        graded = [
            (member, colour)
            for member, colour in graded_colors(MATURITY, unset="Not Assessed", gradient=gradient)
            if member != "Not Assessed"
        ]

        neutral = [(member, colour) for member, colour in graded if _is_neutral(colour)]

        assert not neutral, (
            f"{gradient} puts {neutral} within a hair of grey, which is what the unset member means"
        )

    @pytest.mark.parametrize("gradient", sorted(ATTRIBUTE_GRADIENTS))
    def test_no_point_along_the_scale_reads_as_grey(self, gradient: str) -> None:
        stops = ATTRIBUTE_GRADIENTS[gradient]
        sampled = [color_along_stops(stops, step / 40) for step in range(41)]

        assert not [colour for colour in sampled if _is_neutral(colour)], gradient


def _lab(colour: str) -> tuple[float, float, float]:
    """sRGB to CIE L*a*b*, so two colours can be compared the way an eye compares them.

    Channel arithmetic answers "are these different numbers", which is not the question. Two blues a
    reader cannot tell apart differ by plenty of it; the whole complaint that produced this test was
    about colours whose RGB distance looked ample.
    """
    red, green, blue = (channel / 255 for channel in _channels(colour))

    def linear(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = linear(red), linear(green), linear(blue)
    x = (0.4124 * red + 0.3576 * green + 0.1805 * blue) / 0.95047
    y = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    z = (0.0193 * red + 0.1192 * green + 0.9505 * blue) / 1.08883

    def f(value: float) -> float:
        return value ** (1 / 3) if value > 0.008856 else 7.787 * value + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(first: str, second: str) -> float:
    """CIE76. Cruder than CIEDE2000 and enough for "can these be told apart at a glance"."""
    return sum((a - b) ** 2 for a, b in zip(_lab(first), _lab(second), strict=True)) ** 0.5


#: How far apart adjacent members must be. Around 25 is where two colours stop reading as one at the
#: size a diagram draws an element; the gradients this admits clear 30 at six members and 39 at five.
#: The pair that produced this rule sat at 26 and 27 — measurably different, indistinguishable in the
#: picture, and reported as such.
MINIMUM_ADJACENT_DELTA_E = 25.0

#: How dark the far end may get. A scale's last member is the one a gradient is most tempted to push
#: into the ink to buy separation from its neighbour, and it stops reading as a colour: at L* 13 a
#: navy reads as "off" rather than as the far end of a scale. 25 admits a true navy and refuses black.
MINIMUM_MEMBER_LIGHTNESS = 25.0

#: Beyond this many graded members no two-colour-family gradient keeps them apart, and saying so is
#: better than a threshold that quietly excuses itself. A value set larger than this wants a palette.
MOST_GRADED_MEMBERS_A_GRADIENT_SEPARATES = 6


class TestAdjacentMembersCanBeToldApart:
    """The complaint this encodes: in one gradient the top two members read as one colour, and in the
    other the middle three did. Both were within the ramp's declared range and both were wrong."""

    @pytest.mark.parametrize("gradient", sorted(ATTRIBUTE_GRADIENTS))
    @pytest.mark.parametrize("members", range(2, MOST_GRADED_MEMBERS_A_GRADIENT_SEPARATES + 1))
    def test_no_two_neighbours_read_as_one_colour(self, gradient: str, members: int) -> None:
        names = tuple(f"m{index}" for index in range(members))
        colours = [colour for _member, colour in graded_colors(names, gradient=gradient)]

        gaps = [_delta_e(colours[i], colours[i + 1]) for i in range(len(colours) - 1)]

        assert min(gaps) >= MINIMUM_ADJACENT_DELTA_E, (
            f"{gradient} over {members} members puts neighbours {min(gaps):.0f} apart; "
            f"{[round(gap) for gap in gaps]}"
        )

    @pytest.mark.parametrize("gradient", sorted(ATTRIBUTE_GRADIENTS))
    @pytest.mark.parametrize("members", range(2, MOST_GRADED_MEMBERS_A_GRADIENT_SEPARATES + 1))
    def test_no_member_is_dark_enough_to_read_as_black(self, gradient: str, members: int) -> None:
        """Separation and lightness pull against each other, and this is the side that loses quietly:
        pushing the far end darker widens the last gap and is measured as an improvement."""
        names = tuple(f"m{index}" for index in range(members))
        lightness = {
            colour: _lab(colour)[0] for _member, colour in graded_colors(names, gradient=gradient)
        }

        darkest = min(lightness.items(), key=lambda pair: pair[1])

        assert darkest[1] >= MINIMUM_MEMBER_LIGHTNESS, (
            f"{gradient} over {members} members reaches {darkest[0]} at L*{darkest[1]:.0f}"
        )

    @pytest.mark.parametrize("gradient", sorted(ATTRIBUTE_GRADIENTS))
    def test_the_unset_member_is_apart_from_every_graded_one(self, gradient: str) -> None:
        """White has to be tellable from the scale as well as from the middle of it."""
        colours = dict(graded_colors(MATURITY, unset="Not Assessed", gradient=gradient))
        unset = colours.pop("Not Assessed")

        assert min(_delta_e(unset, colour) for colour in colours.values()) >= MINIMUM_ADJACENT_DELTA_E


class TestAScaleThatRunsTheOtherWay:
    """A gradient's direction belongs to the reader. These run bad to good, which is a maturity
    ladder; a risk band is the same shape upside down, with its high end the bad one. Rather than a
    second table of stops that would drift from the first, each gradient is offered reversed."""

    def test_every_gradient_is_offered_in_both_directions(self) -> None:
        for name in ("red-green", "yellow-blue"):
            assert name in ATTRIBUTE_GRADIENTS
            assert "-".join(reversed(name.split("-"))) in ATTRIBUTE_GRADIENTS

    @pytest.mark.parametrize(("forwards", "backwards"),
                            [("red-green", "green-red"), ("yellow-blue", "blue-yellow")])
    def test_a_reverse_is_its_gradient_read_from_the_other_end(
        self, forwards: str, backwards: str
    ) -> None:
        assert ATTRIBUTE_GRADIENTS[backwards] == tuple(reversed(ATTRIBUTE_GRADIENTS[forwards]))

    @pytest.mark.parametrize(("forwards", "backwards"),
                            [("red-green", "green-red"), ("yellow-blue", "blue-yellow")])
    def test_the_members_come_out_in_the_opposite_order(self, forwards: str, backwards: str) -> None:
        """And the unset member stays white in both: it is not on the scale, so it has no direction."""
        ahead = dict(graded_colors(MATURITY, unset="Not Assessed", gradient=forwards))
        behind = dict(graded_colors(MATURITY, unset="Not Assessed", gradient=backwards))

        graded = [member for member in MATURITY if member != "Not Assessed"]
        assert [ahead[member] for member in graded] == [behind[member] for member in reversed(graded)]
        assert ahead["Not Assessed"] == behind["Not Assessed"] == UNSET_MEMBER_COLOR


class TestTheStopsAvoidMud:
    def test_red_to_green_does_not_run_through_brown(self) -> None:
        """The two-stop version of this ramp put olive and brown across the middle of the scale.
        Sampled against what a bare red-to-green interpolation would have produced."""
        stops = ATTRIBUTE_GRADIENTS["red-green"]
        naive_middle = mix_colors(stops[0], stops[-1], 0.5).lower()

        middle = color_along_stops(stops, 0.5)

        assert middle != naive_middle
        red, green, _blue = _channels(middle)
        assert red + green > 300, f"the middle of the scale came out dark: {middle}"


class TestTheWalkAcrossStops:
    def test_an_unknown_gradient_falls_back_rather_than_failing(self) -> None:
        """A gradient is a reading preference carried in a URL; a stale name still draws a diagram."""
        assert graded_colors(MATURITY, unset="Not Assessed", gradient="no-such-gradient") == (
            graded_colors(MATURITY, unset="Not Assessed", gradient=DEFAULT_ATTRIBUTE_GRADIENT)
        )

    def test_each_stop_is_reached_exactly(self) -> None:
        stops = ATTRIBUTE_GRADIENTS["red-green"]
        segments = len(stops) - 1

        for index, stop in enumerate(stops):
            assert color_along_stops(stops, index / segments) == stop.lower()
