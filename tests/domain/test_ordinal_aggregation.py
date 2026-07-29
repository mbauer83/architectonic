"""Which reductions an ordinal permits, decided by type when the query is loaded.

`min` and `max` pick a member, so they are meaningful and return a member. `sum` and `avg`
combine ranks arithmetically, which treats the gaps between members as known and equal — the
same category error as multiplying ordinals into a single priority number. Rejecting them at
load time rather than at evaluation is what makes the error a query that cannot be saved instead
of a figure someone acts on.
"""

from __future__ import annotations

import pytest

from src.domain.assurance.assessment_scales import CONSEQUENCE_SEVERITY_SCALE
from src.domain.ontology_representation.attribute_scales import ORDINAL_KIND
from src.domain.viewpoints.viewpoint_condition_evaluation import _aggregate
from src.domain.viewpoints.viewpoint_value_types import (
    BindingTypeError,
    ListType,
    ScalarType,
    _aggregate_type,
)


def _ordinal_list() -> ListType:
    return ListType(ScalarType(ORDINAL_KIND))


class TestPermittedReductions:
    @pytest.mark.parametrize("aggregate", ["min", "max"])
    def test_picking_a_member_yields_that_member_s_type(self, aggregate: str) -> None:
        result = _aggregate_type(_ordinal_list(), aggregate)  # type: ignore[arg-type]

        assert result == ScalarType(ORDINAL_KIND), "the result is a member, not a rank"

    def test_counting_is_indifferent_to_the_scale(self) -> None:
        """`count` sizes the set; it never looks at a value, so no scale can make it invalid."""
        assert _aggregate_type(_ordinal_list(), "count") == ScalarType("integer")


class TestRejectedReductions:
    @pytest.mark.parametrize("aggregate", ["sum", "avg"])
    def test_combining_ranks_arithmetically_is_refused(self, aggregate: str) -> None:
        with pytest.raises(BindingTypeError) as excinfo:
            _aggregate_type(_ordinal_list(), aggregate)  # type: ignore[arg-type]

        assert excinfo.value.code == "aggregate-type-mismatch"

    def test_the_refusal_explains_why_rather_than_only_that(self) -> None:
        """An author who is told only "invalid" will look for a workaround; one who is told the
        distance between members is unknown has learnt the rule."""
        with pytest.raises(BindingTypeError) as excinfo:
            _aggregate_type(_ordinal_list(), "avg")  # type: ignore[arg-type]

        message = str(excinfo.value)
        assert "distance between adjacent" in message
        assert "min or max" in message

    def test_numbers_are_unaffected(self) -> None:
        """The restriction follows from the declared level of measurement, not from the reduction."""
        assert _aggregate_type(ListType(ScalarType("integer")), "sum") == ScalarType("integer")
        assert _aggregate_type(ListType(ScalarType("integer")), "avg") == ScalarType("number")


class TestReducingAtEvaluationTime:
    def test_max_over_an_ordinal_ranks_rather_than_sorts_alphabetically(self) -> None:
        values = ("minor", "catastrophic", "moderate")

        result = _aggregate(values, "max", ordinal_scale=CONSEQUENCE_SEVERITY_SCALE)

        assert result == "catastrophic"

    def test_without_a_scale_the_same_values_sort_alphabetically(self) -> None:
        """Shows the scale is what does the work — and why an unmarked severity misleads."""
        values = ("minor", "catastrophic", "moderate")

        assert _aggregate(values, "max") == "moderate"

    def test_min_over_an_ordinal_ranks(self) -> None:
        values = ("major", "minor", "moderate")

        assert _aggregate(values, "min", ordinal_scale=CONSEQUENCE_SEVERITY_SCALE) == "minor"

    def test_an_empty_set_reduces_to_absence_not_to_a_floor_value(self) -> None:
        assert _aggregate((), "max", ordinal_scale=CONSEQUENCE_SEVERITY_SCALE) is None

    def test_counting_still_counts_when_a_scale_is_supplied(self) -> None:
        values = ("minor", "unrecognised")

        assert _aggregate(values, "count", ordinal_scale=CONSEQUENCE_SEVERITY_SCALE) == 2
