"""The Action Priority table: severity-dominant, no arithmetic, and no risk priority number.

The pinned case is `(catastrophic, rare, very-low) ⇒ high`. That single row is where an inverted
detectability scale shows up: read the axis the conventional FMEA way round and `very-low` becomes
"easily detected", which turns the most dangerous row in any analysis into a low priority. It is
asserted explicitly rather than left to the snapshot, so the failure names itself.
"""

from __future__ import annotations

import pytest

from src.domain.assurance.fmea_action_priority import (
    ACTION_PRIORITY_BANDS,
    HIGH,
    INDETERMINATE,
    LOW,
    MEDIUM,
    action_priority,
    insensitive_pairs,
    occurrence_is_decisive,
    priority_table,
    worst_band,
)
from src.domain.assurance.fmea_factors import DETECTABILITY_SCALE, OCCURRENCE_SCALE, SEVERITY_SCALE


class TestSeverityDominates:
    def test_a_catastrophic_undetectable_failure_is_high_however_rare(self) -> None:
        """The pinned row. If this ever reads `low`, the detectability axis has been inverted."""
        assert action_priority("catastrophic", "rare", "very-low") == HIGH

    def test_a_severe_failure_that_would_go_unnoticed_is_high_at_every_occurrence(self) -> None:
        for occurrence in OCCURRENCE_SCALE:
            assert action_priority("major", occurrence, "very-low") == HIGH, occurrence

    def test_a_catastrophic_failure_that_is_not_rare_is_high_even_when_detectable(self) -> None:
        assert action_priority("catastrophic", "possible", "very-high") == HIGH

    def test_a_slight_failure_that_would_be_caught_is_low_at_every_occurrence(self) -> None:
        for occurrence in OCCURRENCE_SCALE:
            assert action_priority("minor", occurrence, "very-high") == LOW, occurrence

    def test_the_middle_of_the_table_is_medium(self) -> None:
        assert action_priority("moderate", "possible", "moderate") == MEDIUM


class TestAMissingFactorIsNotALowPriority:
    @pytest.mark.parametrize(
        ("severity", "occurrence", "detectability"),
        [
            (None, "possible", "moderate"),
            ("major", None, "moderate"),
            ("major", "possible", None),
            (None, None, None),
        ],
    )
    def test_an_absent_factor_that_could_have_mattered_yields_indeterminate(
        self, severity: str | None, occurrence: str | None, detectability: str | None
    ) -> None:
        """An unrated row is a gap to close. Rendering it as `low` is how an un-analysed component
        comes to look safe."""
        assert action_priority(severity, occurrence, detectability) == INDETERMINATE

    def test_a_row_the_surface_never_asked_about_still_gets_its_band(self) -> None:
        """Occurrence is not asked for where it cannot change the answer, so requiring it anyway
        would leave exactly those rows looking unrated forever — the opposite of the intent."""
        assert not occurrence_is_decisive("catastrophic", "very-low")

        assert action_priority("catastrophic", None, "very-low") == HIGH

    def test_a_slight_detectable_row_completes_without_an_occurrence_too(self) -> None:
        assert action_priority("minor", None, "very-high") == LOW

    def test_indeterminate_is_its_own_band(self) -> None:
        assert INDETERMINATE not in (HIGH, MEDIUM, LOW)
        assert INDETERMINATE in ACTION_PRIORITY_BANDS


class TestOccurrenceIsOnlyAskedWhenItMatters:
    def test_the_named_corners_are_insensitive(self) -> None:
        """The two corners the rules exist to settle: a severe outcome nothing would catch is high
        whatever its rate, and a slight outcome that would be caught is low whatever its rate."""
        named_corners = {
            (severity, detectability)
            for severity in ("catastrophic", "major")
            for detectability in ("very-low", "low")
        } | {
            (severity, detectability)
            for severity in ("negligible", "minor")
            for detectability in ("high", "very-high")
        }

        assert named_corners <= set(insensitive_pairs())

    def test_twelve_of_the_twenty_five_pairs_are_insensitive(self) -> None:
        """More than the four-plus-four corners above: `minor` also never varies where detection is
        poor, and the middle of each scale settles on its own. Pinned so a later rule change shows
        up here rather than silently altering which rows get asked for an occurrence."""
        assert len(insensitive_pairs()) == 12

    def test_no_severity_band_is_a_constant(self) -> None:
        """The defect this table was corrected for: with no rule mentioning `moderate`, every
        moderate-severity failure mode came out `medium` whatever its occurrence AND whatever its
        detectability — a fifth of the severity scale where the analysis said nothing at all."""
        for severity in SEVERITY_SCALE:
            bands = {
                action_priority(severity, occurrence, detectability)
                for occurrence in OCCURRENCE_SCALE
                for detectability in DETECTABILITY_SCALE
            }
            assert len(bands) > 1, f"{severity} yields only {bands}"

    def test_a_moderate_failure_that_is_certain_and_unnoticed_is_high(self) -> None:
        assert action_priority("moderate", "almost-certain", "very-low") == HIGH

    def test_a_moderate_failure_that_is_rare_and_caught_is_low(self) -> None:
        assert action_priority("moderate", "rare", "very-high") == LOW

    def test_a_decisive_pair_really_changes_the_band(self) -> None:
        """Guards against the suppression rule being computed from a table that never varies."""
        assert occurrence_is_decisive("catastrophic", "moderate")
        assert action_priority("catastrophic", "rare", "moderate") != action_priority(
            "catastrophic", "likely", "moderate",
        )

    def test_an_insensitive_pair_is_reported_as_such(self) -> None:
        assert not occurrence_is_decisive("major", "very-low")

    def test_occurrence_still_decides_somewhere(self) -> None:
        """If every pair were insensitive the field would never be asked for, which would make the
        factor unreachable rather than economical."""
        total = len(SEVERITY_SCALE) * len(DETECTABILITY_SCALE)

        assert 0 < len(insensitive_pairs()) < total


class TestTheWholeTable:
    def test_every_combination_lands_in_a_real_band(self) -> None:
        table = priority_table()

        assert len(table) == 125
        assert {row[3] for row in table} <= {HIGH, MEDIUM, LOW}

    def test_the_table_is_a_characterization_snapshot(self) -> None:
        """A count per band. Any rule change moves these numbers, which is a reviewable diff rather
        than a silent re-prioritisation of every analysis in the repository."""
        table = priority_table()
        counts = {band: sum(1 for row in table if row[3] == band) for band in (HIGH, MEDIUM, LOW)}

        assert counts == {HIGH: 34, MEDIUM: 61, LOW: 30}

    def test_no_band_is_computed_by_arithmetic(self) -> None:
        """Structural: the module multiplies nothing, so no product can creep back in as a score."""
        import inspect

        from src.domain.assurance import fmea_action_priority

        source = inspect.getsource(fmea_action_priority)
        code = "\n".join(
            line for line in source.splitlines()
            if not line.strip().startswith("#") and not line.strip().startswith('"')
        )
        assert " * " not in code
        assert "rpn" not in code.lower()


class TestRollingUpToOneComponent:
    def test_the_most_urgent_band_wins(self) -> None:
        assert worst_band([LOW, HIGH, MEDIUM]) == HIGH
        assert worst_band([LOW, MEDIUM]) == MEDIUM

    def test_an_unrated_row_never_outranks_a_real_finding(self) -> None:
        """Otherwise the row that needs work is buried under the row nobody has looked at."""
        assert worst_band([INDETERMINATE, LOW]) == LOW

    def test_only_unrated_rows_roll_up_to_indeterminate(self) -> None:
        assert worst_band([INDETERMINATE]) == INDETERMINATE

    def test_no_rows_roll_up_to_nothing(self) -> None:
        assert worst_band([]) is None
