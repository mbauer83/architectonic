"""A reader's colour arrives as text in a URL and ends up inside a PUML declaration.

The compound colour form the renderer writes is `#back:EFBD5D;line:48391C;text:252327` — semicolon
separated. So a colour carrying a semicolon is not a bad colour: it is extra PUML in a body assembled
from a query string. This is the boundary that stops it, and these are the shapes it has to stop.

The refusal is deliberately *quiet*. A malformed pair, a half-given gradient, or a colour that is not
six hex digits is dropped and the element keeps its declared colour; nothing 400s. A stale or
hand-edited URL should still draw the diagram, and a reader whose gradient did not take can see that
from the picture. What must never happen is an unrecognised colour reaching the renderer.
"""

from __future__ import annotations

import pytest

from src.infrastructure.rest.routers.diagrams._reading_lens_request import lens_from_query


def _lens(**over: object):
    return lens_from_query(
        str(over.get("colour_by", "risk_score")),
        list(over.get("printed", [])),  # type: ignore[arg-type]
        str(over.get("ramp", "")),
        list(over.get("key", [])),  # type: ignore[arg-type]
        bool(over.get("legend", False)),
    )


class TestWhatIsRefused:
    @pytest.mark.parametrize(
        "colour",
        [
            "dc2626;line:000000",
            "dc2626;text:ffffff",
            "red",
            "dc262",
            "dc26266",
            "gggggg",
            "",
            "#",
            "dc2626 ;",
            "'>",
        ],
    )
    def test_a_member_colour_that_is_not_six_hex_digits_is_dropped(self, colour: str) -> None:
        assert _lens(key=[f"active:{colour}"]).key == {}

    @pytest.mark.parametrize(
        "ramp",
        ["dc2626;line:000000:fbbf24", "red:blue", "dc2626", "dc2626:", ":fbbf24", "", "dc2626:zzzzzz"],
    )
    def test_a_gradient_is_used_only_when_both_ends_are_colours(self, ramp: str) -> None:
        """Half a gradient is not a gradient. Interpolating from a declared endpoint to a chosen one
        would give a reader a picture they did not ask for and could not explain."""
        assert _lens(ramp=ramp).ramp is None

    def test_a_pair_with_no_colon_names_no_member(self) -> None:
        assert _lens(key=["active"]).key == {}

    def test_a_pair_with_no_member_is_dropped(self) -> None:
        assert _lens(key=[":dc2626"]).key == {}

    def test_a_pair_carrying_a_semicolon_is_refused_whole(self) -> None:
        """Before the split, which is the only place it works. `active:dc2626;line:000000` splits into
        a member ending in `;line` and the valid colour `000000`, so the semicolon would have passed
        the colour check by sitting on the other side of it — leaving a reader a silent mapping for a
        member no entity has."""
        assert _lens(key=["active:dc2626;line:000000"]).key == {}

    def test_a_gradient_carrying_a_semicolon_is_refused_whole(self) -> None:
        assert _lens(ramp="fbbf24:dc2626;line:000000").ramp is None


class TestWhatIsAccepted:
    def test_a_bare_six_digit_colour(self) -> None:
        assert _lens(key=["active:dc2626"]).key == {"active": "#dc2626"}

    def test_a_colour_with_its_hash(self) -> None:
        assert _lens(key=["active:#dc2626"]).key == {"active": "#dc2626"}

    def test_upper_case_is_normalised(self) -> None:
        """One case out, so nothing downstream compares two spellings of one colour."""
        assert _lens(key=["active:DC2626"]).key == {"active": "#dc2626"}

    def test_a_member_containing_a_colon_keeps_it(self) -> None:
        """Split at the *last* colon: a member is a value from the model and may contain one, while a
        hex colour never does. So `tier:gold:dc2626` is the member `tier:gold`, and a member that ends
        in something colour-shaped is read as a member — the split has to resolve the ambiguity one
        way, and this way keeps the model's own values readable."""
        assert _lens(key=["tier:gold:dc2626"]).key == {"tier:gold": "#dc2626"}

    def test_a_gradient_with_both_ends(self) -> None:
        assert _lens(ramp="fbbf24:DC2626").ramp == ("#fbbf24", "#dc2626")

    def test_one_bad_pair_does_not_discard_the_good_ones(self) -> None:
        lens = _lens(key=["active:dc2626", "retired:nope", "planned:#16a34a"])

        assert lens.key == {"active": "#dc2626", "planned": "#16a34a"}


class TestWhatAMappingAloneMeans:
    def test_a_mapping_with_nothing_to_colour_asks_for_nothing(self) -> None:
        """So a stale `ramp` left in a URL cannot force a re-render of a diagram nobody asked to have
        coloured — and cannot cost every ordinary view a PlantUML run."""
        assert _lens(colour_by="", ramp="fbbf24:dc2626", key=["active:dc2626"]).is_empty is True

    def test_a_colouring_with_a_mapping_asks_for_something(self) -> None:
        assert _lens(colour_by="risk_score", ramp="fbbf24:dc2626").is_empty is False


class TestAskingForALegend:
    def test_it_is_one_flag(self) -> None:
        """One control rather than one per mark: which marks a legend can show is the diagram's
        answer, so four controls of which a diagram can act on one are three dead controls."""
        assert _lens(legend=True).legend is True
        assert _lens(legend=False).legend is False

    def test_a_legend_alone_is_a_request(self) -> None:
        """Nothing else can add a legend, so asking for one is asking for a different picture — where
        a colour mapping with nothing to colour asks for nothing."""
        assert _lens(colour_by="", legend=True).is_empty is False


class TestThePrintedList:
    def test_blank_names_are_dropped_and_order_is_kept(self) -> None:
        assert _lens(printed=["owner", " ", "risk_score", "owner"]).printed == ("owner", "risk_score")
