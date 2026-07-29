"""Targeting signals are presented as named inputs and never as one number.

The prohibition is the point. A composite index over "how many things depend on this" and "how
sensitive the data it touches is" needs weights nobody can defend, and would then look
authoritative — the same error as pre-filling a failure rate from a complexity metric. What a
reader gets instead is a count of signals in their worst band and the names of those signals.
"""

from __future__ import annotations

import pytest

from src.domain.assurance.fmea_targeting_bands import (
    TARGETING_BANDS,
    WORST_BAND,
    SignalReading,
    band_by_membership,
    band_by_thresholds,
    sort_key,
    summarize,
)


def _reading(name: str, band: str | None, *, provisional: bool = False) -> SignalReading:
    return SignalReading(name=name, band=band, provisional=provisional)


class TestBandingACount:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0, "minimal"), (1, "low"), (4, "moderate"), (9, "high"), (20, "highest")],
    )
    def test_a_count_lands_in_its_band(self, value: int, expected: str) -> None:
        assert band_by_thresholds(value, [1, 4, 9, 15]) == expected

    def test_zero_is_a_real_reading(self) -> None:
        """"Nothing depends on this" is a finding when the neighbourhood IS modelled."""
        assert band_by_thresholds(0, [1, 4, 9, 15]) == "minimal"

    def test_not_computed_is_not_a_band(self) -> None:
        """The distinction the whole design rests on: absence must not become the floor band."""
        assert band_by_thresholds(None, [1, 4, 9, 15]) is None

    def test_a_wrong_number_of_thresholds_is_refused(self) -> None:
        with pytest.raises(ValueError, match="thresholds"):
            band_by_thresholds(3, [1, 2])


class TestBandingARankedValue:
    def test_the_existing_order_is_restated_not_reinvented(self) -> None:
        ranked = ["Public", "Internal", "Confidential", "Strictly Confidential"]

        assert band_by_membership("Public", ranked) == TARGETING_BANDS[0]
        assert band_by_membership("Strictly Confidential", ranked) == WORST_BAND

    def test_an_absent_value_is_not_banded(self) -> None:
        assert band_by_membership(None, ["Public", "Internal"]) is None

    def test_an_unrecognised_value_is_not_banded(self) -> None:
        """Never the floor: an unclassified value is unknown, not public."""
        assert band_by_membership("Mystery", ["Public", "Internal"]) is None


class TestTheSummaryNamesSignalsRatherThanScoringThem:
    def test_it_counts_and_names_the_worst_band_signals(self) -> None:
        summary = summarize([
            _reading("typed dependents", WORST_BAND),
            _reading("sole provider", WORST_BAND),
            _reading("data sensitivity", "low"),
        ])

        assert summary.worst_band_count == 2
        assert summary.worst_band_signals == ("typed dependents", "sole provider")
        assert summary.headline == (
            "2 of 3 signals in their worst band: typed dependents, sole provider"
        )

    def test_uncomputed_signals_are_excluded_from_the_denominator(self) -> None:
        """Otherwise a thin model quietly improves an element's apparent standing."""
        summary = summarize([_reading("typed dependents", WORST_BAND), _reading("telemetry", None)])

        assert summary.computed_count == 1
        assert summary.headline.startswith("1 of 1")

    def test_nothing_computed_says_so(self) -> None:
        summary = summarize([_reading("typed dependents", None)])

        assert summary.headline == "no targeting signals could be computed"

    def test_a_quiet_element_reads_as_quiet_rather_than_as_unknown(self) -> None:
        summary = summarize([_reading("typed dependents", "low")])

        assert summary.headline == "0 of 1 signals in their worst band"

    def test_provisional_carries_up_to_the_summary(self) -> None:
        summary = summarize([_reading("typed dependents", "high", provisional=True)])

        assert summary.provisional

    def test_the_summary_exposes_no_composite_value(self) -> None:
        """Structurally: there is no total, index or score attribute to render by accident."""
        summary = summarize([_reading("typed dependents", WORST_BAND)])
        names = set(vars(summary))

        assert not {"score", "total", "index", "composite", "rating"} & names


class TestWorklistOrdering:
    def test_more_signals_in_their_worst_band_sort_first(self) -> None:
        loud = summarize([_reading("a", WORST_BAND), _reading("b", WORST_BAND)])
        quiet = summarize([_reading("a", WORST_BAND), _reading("b", "low")])

        assert sorted([quiet, loud], key=sort_key)[0] is loud

    def test_a_thinly_modelled_element_does_not_outrank_a_well_modelled_one(self) -> None:
        """A thin picture is a modelling gap, not a quieter risk."""
        thin = summarize([_reading("a", WORST_BAND), _reading("b", None)])
        full = summarize([_reading("a", WORST_BAND), _reading("b", "low")])

        assert sorted([thin, full], key=sort_key)[0] is full

    def test_the_sort_key_is_never_the_headline(self) -> None:
        """It orders and is never shown; the headline is what a reader sees."""
        summary = summarize([_reading("a", WORST_BAND)])

        assert str(sort_key(summary)) not in summary.headline
