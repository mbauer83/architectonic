"""Presenting analysis-targeting signals: named inputs, banded, never a single score.

These signals answer "where should I spend analysis effort", which is a genuinely useful question
and a different one from "how bad is this failure mode". Keeping them apart is the whole design:

**They never compose into one number.** A composite needs weights, and no defensible weighting
exists between "how many things depend on this" and "how sensitive the data it touches is" — they
are not commensurable. A single index would look authoritative and be arbitrary, which is the same
error as pre-filling occurrence from a complexity metric. So a component's summary is *"N of 5
signals in their worst band"* plus the names of those signals: sortable, and impossible to mistake
for a rating of the failure itself.

**They are never a factor.** No signal is persisted as a factor value, defaulted into one, or
offered as one. An element with no telemetry deserves a look; that is not a claim about how often it
fails.

**Absence is absence.** A signal that cannot be computed contributes nothing. A zero would read as
"nothing depends on this, it is simple and safe", which is exactly the wrong reading of a sparsely
modelled corner of the architecture — and a sparsely modelled corner is where risk hides.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: Five bands, weakest attention-worthiness first, so a band name reads the same way in every
#: signal: the last band always means "this one is worth a look".
TARGETING_BANDS: tuple[str, ...] = ("minimal", "low", "moderate", "high", "highest")

WORST_BAND = TARGETING_BANDS[-1]


@dataclass(frozen=True)
class SignalReading:
    """One signal's value for one element, with how much of it could be computed."""

    name: str
    band: str | None
    """None when the signal could not be computed. Never a floor band."""
    detail: str = ""
    """What the value is, in the analyst's words — the number, the id, the classification."""
    witness: tuple[str, ...] = ()
    """The path or the ids that produced it, so the reading can be checked."""
    provisional: bool = False
    """True when computed over a neighbourhood that is only partly modelled. The value stands, but
    it rests on less than it appears to."""


@dataclass(frozen=True)
class TargetingSummary:
    """A component's targeting picture: how many signals are in their worst band, and which."""

    readings: tuple[SignalReading, ...]
    worst_band_count: int
    worst_band_signals: tuple[str, ...]
    computed_count: int
    provisional: bool

    @property
    def headline(self) -> str:
        """The one line a worklist shows. Names the signals rather than scoring them."""
        if not self.computed_count:
            return "no targeting signals could be computed"
        if not self.worst_band_count:
            return f"0 of {self.computed_count} signals in their worst band"
        named = ", ".join(self.worst_band_signals)
        return f"{self.worst_band_count} of {self.computed_count} signals in their worst band: {named}"


def band_by_thresholds(value: int | None, thresholds: Sequence[int]) -> str | None:
    """Band a count against four ascending thresholds, or None when there is no value.

    Thresholds are the lower bounds of bands 2..5, so a value below the first is `minimal`. Passing
    a value of zero is meaningful and bands as `minimal`; passing None means *not computed*, and the
    two must not be conflated — which is why this takes an optional and returns one.
    """
    if value is None:
        return None
    if len(thresholds) != len(TARGETING_BANDS) - 1:
        raise ValueError(f"expected {len(TARGETING_BANDS) - 1} thresholds, got {len(thresholds)}")
    crossed = sum(1 for threshold in thresholds if value >= threshold)
    return TARGETING_BANDS[crossed]


def band_by_membership(value: str | None, ranked_values: Sequence[str]) -> str | None:
    """Band a categorical value by its position in a ranked list, or None when absent.

    Used where a signal is already an ordered vocabulary — a data classification, a declared
    telemetry level — so the banding restates the existing order rather than inventing one.
    """
    if value is None or value not in ranked_values:
        return None
    position = list(ranked_values).index(value)
    span = max(len(ranked_values) - 1, 1)
    return TARGETING_BANDS[round(position * (len(TARGETING_BANDS) - 1) / span)]


def summarize(readings: Sequence[SignalReading]) -> TargetingSummary:
    """Roll several readings into one sortable line, without adding them up."""
    computed = [reading for reading in readings if reading.band is not None]
    worst = [reading.name for reading in computed if reading.band == WORST_BAND]
    return TargetingSummary(
        readings=tuple(readings),
        worst_band_count=len(worst),
        worst_band_signals=tuple(worst),
        computed_count=len(computed),
        provisional=any(reading.provisional for reading in computed),
    )


def sort_key(summary: TargetingSummary) -> tuple[int, int, int]:
    """Worklist ordering: most signals in their worst band first.

    A sort key, not a score: it orders and is never shown as a value. Ties fall back to how many
    signals could be computed at all, so a well-modelled element outranks one whose picture is thin
    — the thin one is a modelling gap rather than a quieter risk.
    """
    return (-summary.worst_band_count, -summary.computed_count, 1 if summary.provisional else 0)


def readings_by_name(readings: Sequence[SignalReading]) -> Mapping[str, SignalReading]:
    return {reading.name: reading for reading in readings}
