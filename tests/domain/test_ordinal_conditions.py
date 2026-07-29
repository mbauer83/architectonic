"""Ordering an ordinal attribute: by declared rank, within one scale, or not at all.

Three rules, each with a way of being wrong that produces a plausible answer rather than an
error. Ordering by value would sort severities alphabetically. Ordering across two scales would
compare positions that count different things. Ordering a value absent from the scale would place
it somewhere it does not belong. All three are settled here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.assurance.assessment_scales import CONSEQUENCE_SEVERITY_SCALE, LIKELIHOOD_SCALE
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.attribute_scales import ORDINAL_KIND
from src.domain.viewpoints.viewpoint_condition_evaluation import evaluate_attribute_condition
from src.domain.viewpoints.viewpoint_condition_validation import (
    RegistrySnapshot,
    attribute_ordinal_scale,
    validate_condition,
)
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, ValueRef

_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"risk"}),
    known_connection_types=frozenset(),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={
        "impact": ORDINAL_KIND,
        "residual_impact": ORDINAL_KIND,
        "likelihood": ORDINAL_KIND,
        "owner": "string",
        "unranked_grade": ORDINAL_KIND,
    },
    connection_attribute_types={},
    entity_attribute_enums={
        "impact": CONSEQUENCE_SEVERITY_SCALE,
        "residual_impact": CONSEQUENCE_SEVERITY_SCALE,
        "likelihood": LIKELIHOOD_SCALE,
    },
)


def _entity(**attributes: object) -> EntityRecord:
    return EntityRecord(  # type: ignore[arg-type]
        artifact_id="RSK@001",
        artifact_type="risk",
        name="A risk",
        version="1.0",
        status="draft",
        domain="application",
        subdomain="",
        path=Path("/fake/risk.md"),
        keywords=(),
        extra=dict(attributes),
        content_text="",
        display_blocks={},
        display_label="A risk",
        display_alias="",
    )


class _NoReads:
    def get_entity(self, _artifact_id: str) -> EntityRecord | None:
        return None

    def entities(self) -> tuple[EntityRecord, ...]:
        return ()

    def connections(self) -> tuple[object, ...]:
        return ()


def _matches(attribute: str, comparator: str, value: object, **attributes: object) -> bool:
    condition = AttributeCondition(
        attribute=attribute, comparator=comparator, value=ValueRef(kind="literal", literal=value),
    )
    outcome = evaluate_attribute_condition(
        condition,
        record=_entity(**attributes),
        context="entity",
        read_access=_NoReads(),  # type: ignore[arg-type]
        registries=_REGISTRIES,
        connection=None,
    )
    return outcome.matched


def _issue_codes(condition: AttributeCondition) -> list[str]:
    return [
        issue.code
        for issue in validate_condition(condition, path="/q", context="entity", registries=_REGISTRIES)
    ]


class TestTheScaleIsFoundFromTheDeclaredEnum:
    def test_an_ordinal_attribute_resolves_to_its_ranked_members(self) -> None:
        """The enum already recorded for the value picker IS the scale — no second list."""
        scale = attribute_ordinal_scale("impact", context="entity", registries=_REGISTRIES)

        assert scale == CONSEQUENCE_SEVERITY_SCALE

    def test_a_non_ordinal_attribute_has_no_scale(self) -> None:
        assert attribute_ordinal_scale("owner", context="entity", registries=_REGISTRIES) is None


class TestOrderingComparatorsAreAllowedOnOrdinals:
    @pytest.mark.parametrize("comparator", ["lt", "lte", "gt", "gte"])
    def test_an_ordinal_accepts_the_ordering_comparators(self, comparator: str) -> None:
        condition = AttributeCondition(
            attribute="impact", comparator=comparator, value=ValueRef(kind="literal", literal="major"),
        )

        assert "operator-type-mismatch" not in _issue_codes(condition)

    def test_a_plain_string_still_rejects_them(self) -> None:
        """Ordinality is what licenses ordering, so an undeclared attribute is unchanged."""
        condition = AttributeCondition(
            attribute="owner", comparator="gt", value=ValueRef(kind="literal", literal="alice"),
        )

        assert "operator-type-mismatch" in _issue_codes(condition)

    def test_an_ordinal_without_a_ranked_value_list_cannot_be_ordered(self) -> None:
        """Declaring a rank without members to rank leaves nothing to compare against, and
        guessing an order would invent the very thing the declaration was meant to state."""
        condition = AttributeCondition(
            attribute="unranked_grade", comparator="gt", value=ValueRef(kind="literal", literal="high"),
        )

        assert "ordinal-scale-missing" in _issue_codes(condition)


class TestComparingTwoOrdinalsRequiresOneScale:
    def test_two_attributes_on_the_same_scale_may_be_ordered(self) -> None:
        condition = AttributeCondition(
            attribute="impact",
            comparator="gt",
            value=ValueRef(kind="attribute_of_self", attribute="residual_impact"),
        )

        assert _issue_codes(condition) == []

    def test_two_attributes_on_different_scales_are_refused(self) -> None:
        """Both scales are five-point and both rank 0..4, so the ranks compare cleanly and mean
        nothing — which is why this has to be refused rather than left to evaluation."""
        condition = AttributeCondition(
            attribute="impact",
            comparator="gt",
            value=ValueRef(kind="attribute_of_self", attribute="likelihood"),
        )

        assert "ordinal-scale-mismatch" in _issue_codes(condition)

    def test_equality_across_scales_is_left_alone(self) -> None:
        """`eq` compares members, not ranks, so it asserts something well-defined (and false)."""
        condition = AttributeCondition(
            attribute="impact",
            comparator="eq",
            value=ValueRef(kind="attribute_of_self", attribute="likelihood"),
        )

        assert "ordinal-scale-mismatch" not in _issue_codes(condition)


class TestEvaluationOrdersByRank:
    def test_a_worse_severity_is_greater_even_though_it_sorts_earlier(self) -> None:
        """'catastrophic' < 'minor' alphabetically; by rank it is the greater. This single case is
        the difference between a correct heat map and a confidently wrong one."""
        assert _matches("impact", "gt", "minor", impact="catastrophic")
        assert not _matches("impact", "gt", "catastrophic", impact="minor")

    @pytest.mark.parametrize(
        ("comparator", "expected"),
        [("lt", True), ("lte", True), ("gt", False), ("gte", False)],
    )
    def test_each_ordering_comparator_uses_the_rank(self, comparator: str, expected: bool) -> None:
        assert _matches("impact", comparator, "major", impact="minor") is expected

    def test_equal_ranks_satisfy_the_inclusive_comparators_only(self) -> None:
        assert _matches("impact", "lte", "major", impact="major")
        assert _matches("impact", "gte", "major", impact="major")
        assert not _matches("impact", "lt", "major", impact="major")

    def test_a_value_outside_the_scale_matches_no_ordering(self) -> None:
        """Unranked, so it participates in no comparison — rather than ranking as the least
        severe member, which would hide it under every "at least minor" filter."""
        assert not _matches("impact", "gt", "negligible", impact="apocalyptic")
        assert not _matches("impact", "lt", "catastrophic", impact="apocalyptic")

    def test_comparing_against_a_value_outside_the_scale_matches_nothing(self) -> None:
        assert not _matches("impact", "gt", "unrecognised", impact="catastrophic")

    def test_an_unrankable_stored_value_is_reported_as_drift(self) -> None:
        """Silently not matching would leave the row invisible with no explanation; the data and
        the schema genuinely disagree, which is what the drift channel is for."""
        condition = AttributeCondition(
            attribute="impact", comparator="gt", value=ValueRef(kind="literal", literal="minor"),
        )

        outcome = evaluate_attribute_condition(
            condition,
            record=_entity(impact="apocalyptic"),
            context="entity",
            read_access=_NoReads(),  # type: ignore[arg-type]
            registries=_REGISTRIES,
            connection=None,
        )

        assert not outcome.matched
        assert "impact" in outcome.schema_drift

    def test_a_rankable_stored_value_reports_no_drift(self) -> None:
        condition = AttributeCondition(
            attribute="impact", comparator="gt", value=ValueRef(kind="literal", literal="minor"),
        )

        outcome = evaluate_attribute_condition(
            condition,
            record=_entity(impact="major"),
            context="entity",
            read_access=_NoReads(),  # type: ignore[arg-type]
            registries=_REGISTRIES,
            connection=None,
        )

        assert outcome.matched
        assert not outcome.schema_drift

    def test_equality_still_compares_members(self) -> None:
        """Ranking governs ordering only; membership questions are unaffected by it."""
        assert _matches("impact", "eq", "catastrophic", impact="catastrophic")
        assert _matches("impact", "in", ["minor", "catastrophic"], impact="catastrophic")
