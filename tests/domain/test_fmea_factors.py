"""When a factor judgement applies, and what a reader sees when it stops applying.

The load-bearing case is the one that looks like nothing happened: a judgement whose *value* is
unchanged but whose *basis* has moved. Comparing values would call that unchanged and keep driving
a priority from a picture of the model that no longer exists — a loss swapped for another of equal
severity, or a detecting control swapped for one at the same evidence tier. Keying the judgement to
its basis is what makes it stop applying, and the derived value stand again.
"""

from __future__ import annotations

from src.domain.assurance.assessment_scales import CONSEQUENCE_SEVERITY_SCALE, LIKELIHOOD_SCALE
from src.domain.assurance.fmea_factors import (
    BASIS_ABSENT,
    BASIS_ASSERTED,
    BASIS_DERIVED,
    BASIS_DERIVED_SUPERSEDING_AN_ASSESSMENT,
    DETECTABILITY,
    DETECTABILITY_SCALE,
    FMEA_FACTORS,
    OCCURRENCE,
    OCCURRENCE_SCALE,
    SEVERITY,
    SEVERITY_SCALE,
    FactorAssessment,
    compute_basis_digest,
    effective_factor,
    validate_factor_assessment,
)


def _assessment(
    *, value: str, basis: str, revision: int = 1, factor: str = OCCURRENCE
) -> FactorAssessment:
    return FactorAssessment(
        node_id="FMD@1",
        factor=factor,
        basis_digest=basis,
        revision=revision,
        value=value,
        justification="comparable component fails about twice a year",
        author="analyst",
        created_at="2026-07-26T00:00:00Z",
    )


class TestTheScalesAreReusedNotRestated:
    def test_severity_rates_the_loss_on_the_consequence_scale(self) -> None:
        """One quantity, one scale, whether it is reached from a risk or from a failure mode."""
        assert SEVERITY_SCALE == CONSEQUENCE_SEVERITY_SCALE

    def test_occurrence_is_the_existing_frequency_scale(self) -> None:
        """A second five-point frequency vocabulary would differ from this one eventually."""
        assert OCCURRENCE_SCALE == LIKELIHOOD_SCALE

    def test_detectability_runs_from_least_to_most_detectable(self) -> None:
        """Named for the direction it carries: conventional FMEA 'D' numbers run the other way, and
        the decision table inverts it exactly once, where the table is defined."""
        assert DETECTABILITY_SCALE[0] == "very-low"
        assert DETECTABILITY_SCALE[-1] == "very-high"

    def test_the_three_factors_are_the_three(self) -> None:
        assert FMEA_FACTORS == (SEVERITY, OCCURRENCE, DETECTABILITY)


class TestAnAssertionMustBeCheckable:
    def test_a_complete_assertion_passes(self) -> None:
        assert validate_factor_assessment(OCCURRENCE, "possible", "seen twice in staging", "ana") == []

    def test_a_missing_rationale_is_rejected(self) -> None:
        """A factor value moves a priority band, and a band with no stated reason is the number
        that gets argued about in review and cannot be defended."""
        errors = validate_factor_assessment(OCCURRENCE, "possible", "   ", "analyst")

        assert [e.field for e in errors] == ["justification"]

    def test_a_missing_author_is_rejected(self) -> None:
        errors = validate_factor_assessment(OCCURRENCE, "possible", "seen twice", "")

        assert [e.field for e in errors] == ["author"]

    def test_a_value_outside_the_factor_s_scale_is_rejected(self) -> None:
        errors = validate_factor_assessment(OCCURRENCE, "catastrophic", "seen twice", "analyst")

        assert [e.field for e in errors] == ["value"]
        assert "not a member of the occurrence scale" in errors[0].message

    def test_an_unknown_factor_is_rejected(self) -> None:
        errors = validate_factor_assessment("rpn", "5", "computed", "analyst")

        assert [e.field for e in errors] == ["factor"]


class TestTheBasisDigest:
    def test_the_same_inputs_digest_the_same(self) -> None:
        assert compute_basis_digest(["LSS@1:major"]) == compute_basis_digest(["LSS@1:major"])

    def test_different_inputs_digest_differently(self) -> None:
        assert compute_basis_digest(["LSS@1:major"]) != compute_basis_digest(["LSS@1:minor"])

    def test_a_swapped_loss_of_equal_severity_still_moves_the_digest(self) -> None:
        """The case value comparison cannot see: same severity, different consequence picture."""
        assert compute_basis_digest(["LSS@1:major"]) != compute_basis_digest(["LSS@2:major"])

    def test_the_digest_does_not_depend_on_mapping_order(self) -> None:
        """The digest is an identity; one that varied with dict ordering would retire judgements at
        random."""
        first = compute_basis_digest([{"loss": "LSS@1", "severity": "major"}])
        second = compute_basis_digest([{"severity": "major", "loss": "LSS@1"}])

        assert first == second


class TestWhichValueAReaderSees:
    def test_an_assertion_against_the_current_basis_wins(self) -> None:
        result = effective_factor(
            OCCURRENCE,
            assessments=[_assessment(value="likely", basis="basis-a")],
            derived_value=None,
            current_basis_digest="basis-a",
        )

        assert (result.value, result.basis) == ("likely", BASIS_ASSERTED)

    def test_the_latest_revision_against_the_current_basis_wins(self) -> None:
        result = effective_factor(
            OCCURRENCE,
            assessments=[
                _assessment(value="possible", basis="basis-a", revision=1),
                _assessment(value="likely", basis="basis-a", revision=2),
            ],
            derived_value=None,
            current_basis_digest="basis-a",
        )

        assert result.value == "likely"

    def test_the_derived_value_stands_when_no_assertion_exists(self) -> None:
        result = effective_factor(
            SEVERITY, assessments=[], derived_value="major", current_basis_digest="basis-a",
        )

        assert (result.value, result.basis) == ("major", BASIS_DERIVED)

    def test_a_judgement_made_against_a_moved_basis_stops_applying(self) -> None:
        """No staleness flag is needed: applicability is a fact about which basis the row carries."""
        result = effective_factor(
            SEVERITY,
            assessments=[_assessment(value="minor", basis="basis-a", factor=SEVERITY)],
            derived_value="catastrophic",
            current_basis_digest="basis-b",
        )

        assert result.value == "catastrophic"
        assert result.basis == BASIS_DERIVED_SUPERSEDING_AN_ASSESSMENT

    def test_the_judgement_that_applies_stays_visible_too(self) -> None:
        """The asymmetry that made a recorded rationale unreadable: the judgement that no longer
        applies was carried whole, and the one currently setting the band was reduced to its
        value. `validate_factor_assessment` refuses a value with no rationale, so the product
        demanded a reason it could not then answer with."""
        applying = _assessment(value="likely", basis="basis-a")

        result = effective_factor(
            OCCURRENCE, assessments=[applying], derived_value=None, current_basis_digest="basis-a",
        )

        assert result.assessment == applying

    def test_a_derived_value_carries_no_judgement_because_nobody_made_one(self) -> None:
        result = effective_factor(
            SEVERITY, assessments=[], derived_value="major", current_basis_digest="basis-a",
        )

        assert result.assessment is None

    def test_a_value_whose_judgement_has_been_superseded_is_nobody_s_assertion_now(self) -> None:
        """The two fields answer different questions, so a superseded judgement must not appear as
        the one that applies — the value on show is the model's, not that author's."""
        result = effective_factor(
            SEVERITY,
            assessments=[_assessment(value="minor", basis="basis-a", factor=SEVERITY)],
            derived_value="catastrophic",
            current_basis_digest="basis-b",
        )

        assert result.assessment is None
        assert result.superseded_assessment is not None

    def test_the_superseded_judgement_stays_visible(self) -> None:
        """Retained and shown, not discarded: the reader needs to know a person once decided this,
        and what they decided it against."""
        superseded = _assessment(value="minor", basis="basis-a", factor=SEVERITY)

        result = effective_factor(
            SEVERITY,
            assessments=[superseded],
            derived_value="catastrophic",
            current_basis_digest="basis-b",
        )

        assert result.superseded_assessment == superseded

    def test_a_judgement_with_the_same_value_but_a_moved_basis_also_stops_applying(self) -> None:
        """The whole reason the digest is in the key. Nothing about the value has changed, so any
        value-based check would let this keep driving a priority."""
        result = effective_factor(
            SEVERITY,
            assessments=[_assessment(value="major", basis="basis-a", factor=SEVERITY)],
            derived_value="major",
            current_basis_digest="basis-b",
        )

        assert result.basis == BASIS_DERIVED_SUPERSEDING_AN_ASSESSMENT, (
            "an unchanged value must not disguise a changed basis"
        )

    def test_no_assertion_and_no_derivation_is_absent_not_a_default(self) -> None:
        result = effective_factor(
            OCCURRENCE, assessments=[], derived_value=None, current_basis_digest="basis-a",
        )

        assert result.value is None
        assert result.basis == BASIS_ABSENT

    def test_a_superseded_judgement_survives_even_with_nothing_derived(self) -> None:
        superseded = _assessment(value="likely", basis="basis-a")

        result = effective_factor(
            OCCURRENCE,
            assessments=[superseded],
            derived_value=None,
            current_basis_digest="basis-b",
        )

        assert result.basis == BASIS_ABSENT
        assert result.superseded_assessment == superseded
