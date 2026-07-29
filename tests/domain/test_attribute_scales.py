"""Ordinal scales: what a declared rank means, and what it refuses to mean.

The rules under test all exist to stop a rank being mistaken for a quantity. A position in an
enum orders its members and nothing more: it does not measure the distance between them, it does
not carry across to another enum, and a value with no position has no rank rather than the lowest
one.
"""

from __future__ import annotations

from src.domain.assurance.assessment_scales import CONSEQUENCE_SEVERITY_SCALE, LIKELIHOOD_SCALE
from src.domain.ontology_representation.attribute_scales import (
    ORDINAL_KIND,
    ORDINAL_SCALE,
    SCALE_KEYWORD,
    declared_scale,
    declares_ordinal,
    ordinal_extreme,
    ordinal_rank,
    ordinal_scales_match,
)


class TestDeclaringTheScale:
    def test_a_property_declaring_ordinal_is_recognised(self) -> None:
        prop = {"type": "string", "enum": list(CONSEQUENCE_SEVERITY_SCALE), SCALE_KEYWORD: ORDINAL_SCALE}

        assert declares_ordinal(prop)
        assert declared_scale(prop) == ORDINAL_SCALE

    def test_an_undeclared_property_is_not_ordinal(self) -> None:
        """Nominal is the absence of a declaration, so a plain string enum stays unranked."""
        assert not declares_ordinal({"type": "string", "enum": ["red", "green"]})
        assert declared_scale({"type": "string"}) is None

    def test_a_missing_or_malformed_property_is_not_ordinal(self) -> None:
        assert not declares_ordinal(None)
        assert not declares_ordinal({SCALE_KEYWORD: ""})
        assert declared_scale("not a mapping") is None  # type: ignore[arg-type]

    def test_the_kind_is_its_own_scalar_kind(self) -> None:
        """Ordinality is decided by type, so nothing has to inspect individual values."""
        assert ORDINAL_KIND == "ordinal"


class TestRank:
    def test_rank_is_the_position_in_the_declared_enum(self) -> None:
        assert ordinal_rank("negligible", CONSEQUENCE_SEVERITY_SCALE) == 0
        assert ordinal_rank("catastrophic", CONSEQUENCE_SEVERITY_SCALE) == 4

    def test_a_value_outside_the_enum_has_no_rank(self) -> None:
        """Never zero: zero is the LOWEST member, so an unrecognised value would read as benign —
        and a sparsely populated attribute is exactly where that misreading is dangerous."""
        assert ordinal_rank("severe", CONSEQUENCE_SEVERITY_SCALE) is None

    def test_a_non_string_value_has_no_rank(self) -> None:
        assert ordinal_rank(3, CONSEQUENCE_SEVERITY_SCALE) is None
        assert ordinal_rank(None, CONSEQUENCE_SEVERITY_SCALE) is None


class TestChoosingAMember:
    def test_max_returns_the_worst_member_not_the_alphabetical_last(self) -> None:
        """Alphabetically 'moderate' is last of these three; by rank 'catastrophic' is worst."""
        values = ["minor", "catastrophic", "moderate"]

        assert ordinal_extreme(values, highest=True, scale=CONSEQUENCE_SEVERITY_SCALE) == "catastrophic"

    def test_min_returns_the_least_severe_member(self) -> None:
        values = ["major", "minor", "moderate"]

        assert ordinal_extreme(values, highest=False, scale=CONSEQUENCE_SEVERITY_SCALE) == "minor"

    def test_the_member_is_returned_rather_than_its_rank(self) -> None:
        chosen = ordinal_extreme(["minor"], highest=True, scale=CONSEQUENCE_SEVERITY_SCALE)

        assert chosen == "minor", "a position is how the choice was made, not the value chosen"

    def test_unranked_values_take_no_part(self) -> None:
        values = ["severe", "minor", "apocalyptic"]

        assert ordinal_extreme(values, highest=True, scale=CONSEQUENCE_SEVERITY_SCALE) == "minor"

    def test_nothing_ranked_yields_absence(self) -> None:
        assert ordinal_extreme(["severe"], highest=True, scale=CONSEQUENCE_SEVERITY_SCALE) is None
        assert ordinal_extreme([], highest=True, scale=CONSEQUENCE_SEVERITY_SCALE) is None


class TestCommensurability:
    def test_the_same_scale_is_comparable_with_itself(self) -> None:
        assert ordinal_scales_match(CONSEQUENCE_SEVERITY_SCALE, CONSEQUENCE_SEVERITY_SCALE)

    def test_two_different_scales_are_not_comparable(self) -> None:
        """Both are five-point, and both rank 0..4 — which is exactly why length cannot decide it."""
        assert len(CONSEQUENCE_SEVERITY_SCALE) == len(LIKELIHOOD_SCALE)
        assert not ordinal_scales_match(CONSEQUENCE_SEVERITY_SCALE, LIKELIHOOD_SCALE)

    def test_the_same_members_in_a_different_order_are_not_comparable(self) -> None:
        """Reordering changes every rank, so this is the confusion most worth refusing."""
        reversed_scale = tuple(reversed(CONSEQUENCE_SEVERITY_SCALE))

        assert not ordinal_scales_match(CONSEQUENCE_SEVERITY_SCALE, reversed_scale)

    def test_an_absent_scale_is_comparable_with_nothing(self) -> None:
        assert not ordinal_scales_match(CONSEQUENCE_SEVERITY_SCALE, None)
        assert not ordinal_scales_match(None, None)
