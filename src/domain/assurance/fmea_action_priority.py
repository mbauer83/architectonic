"""Action Priority: a decision table over the three factors, and never arithmetic.

There is no risk priority number here, and its absence is a decision rather than an omission.
Multiplying severity by occurrence by detectability treats three ordinals as if they were ratio
quantities, which they are not: the step from `major` to `catastrophic` is not the same size as the
step from `minor` to `moderate`, so the product measures nothing. It also conceals what it claims to
rank — a 10·1·1 and a 1·10·1 share a score of 10 while describing completely different situations,
one of them catastrophic. AIAG-VDA replaced the number with a decision table in 2019 for these
reasons, and this follows that.

**Severity-dominant by construction.** A catastrophic outcome that nothing would detect is high
priority however rarely it happens, because rarity is no comfort when the consequence is
unrecoverable and nobody would see it coming.

**The detectability axis runs the conventional way round from FMEA's.** `detectability` rates how
detectable the failure is, so *higher is better*; conventional "D" numbers rate worse detection
higher. The inversion happens here, once, where the table is written — which is why the bands read
`very-low` for "nothing would catch this".
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal, TypeAlias, get_args

from src.domain.assurance.fmea_factors import DETECTABILITY_SCALE, OCCURRENCE_SCALE, SEVERITY_SCALE

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

#: No band can be assigned, because at least one factor has no value. Deliberately its own band
#: rather than a default: a row nobody has rated is not a low-priority row, and rendering it as one
#: is how an un-analysed component comes to look safe.
INDETERMINATE = "indeterminate"

#: The bands, at type level as well, so the matrix contract publishes the vocabulary rather than a
#: bare string. `indeterminate` is one of them and not an absence: an unrated cell must never read as
#: a low-priority one.
ActionPriority: TypeAlias = Literal["high", "medium", "low", "indeterminate"]
ACTION_PRIORITY_BANDS: tuple[ActionPriority, ...] = get_args(ActionPriority)

_SEVERE = frozenset({"catastrophic", "major"})
_SLIGHT = frozenset({"negligible", "minor"})
_POOR_DETECTION = frozenset({"very-low", "low"})
_GOOD_DETECTION = frozenset({"high", "very-high"})
_FREQUENT = frozenset({"possible", "likely", "almost-certain"})
_INFREQUENT = frozenset({"rare", "unlikely"})

#: Ordered rules; the first whose predicate holds decides the band. Written as data rather than as
#: a chain of branches so the whole table can be read, and snapshotted, in one place.
_RULES: tuple[tuple[Callable[[str, str, str], bool], str], ...] = (
    # A severe outcome that would go unnoticed: no occurrence value can make this acceptable.
    (lambda s, o, d: s in _SEVERE and d in _POOR_DETECTION, HIGH),
    # A catastrophic outcome that is not rare.
    (lambda s, o, d: s == "catastrophic" and o in _FREQUENT, HIGH),
    # A severe outcome that is all but certain.
    (lambda s, o, d: s in _SEVERE and o == "almost-certain", HIGH),
    # A moderate outcome that is all but certain and would go unnoticed. Without this and the
    # rule below, no rule mentions moderate severity at all, and every moderate failure mode
    # lands on the default band whatever its occurrence and detectability — a fifth of the
    # severity scale where the analysis produces a constant and so says nothing.
    (lambda s, o, d: s == "moderate" and d in _POOR_DETECTION and o == "almost-certain", HIGH),
    # A moderate outcome that is uncommon and would be caught.
    (lambda s, o, d: s == "moderate" and d in _GOOD_DETECTION and o in _INFREQUENT, LOW),
    # A slight outcome that would be caught.
    (lambda s, o, d: s in _SLIGHT and d in _GOOD_DETECTION, LOW),
    # A negligible outcome that is also uncommon.
    (lambda s, o, d: s == "negligible" and o in _INFREQUENT, LOW),
)


def _band(severity: str, occurrence: str, detectability: str) -> str:
    return next(
        (band for predicate, band in _RULES if predicate(severity, occurrence, detectability)),
        MEDIUM,
    )


def action_priority(
    severity: str | None, occurrence: str | None, detectability: str | None
) -> str:
    """The priority band for one failure mode, or `indeterminate` when it cannot be decided.

    A *missing* factor only forces `indeterminate` when knowing it could have changed the answer.
    Where the severity/detectability pair fixes the band on its own, the row is complete with no
    occurrence at all — which is the point of not asking for one there. Requiring it anyway would
    leave a row that the surface deliberately did not ask about looking unrated forever.
    """
    if severity is None or detectability is None:
        return INDETERMINATE
    if occurrence is not None:
        return _band(severity, occurrence, detectability)
    settled = {_band(severity, candidate, detectability) for candidate in OCCURRENCE_SCALE}
    return settled.pop() if len(settled) == 1 else INDETERMINATE


def occurrence_is_decisive(severity: str, detectability: str) -> bool:
    """Whether any occurrence value could change the band for this severity/detectability pair.

    Severity and detectability are both derived, so the answer is known *before* anyone is asked.
    Where it is false the field is not shown at all: asking for a judgement that cannot matter
    teaches people to answer carelessly, and those same people then answer the rows where it does
    matter.
    """
    return len({_band(severity, occurrence, detectability) for occurrence in OCCURRENCE_SCALE}) > 1


def insensitive_pairs() -> tuple[tuple[str, str], ...]:
    """Every (severity, detectability) pair for which occurrence cannot change the outcome."""
    return tuple(
        (severity, detectability)
        for severity in SEVERITY_SCALE
        for detectability in DETECTABILITY_SCALE
        if not occurrence_is_decisive(severity, detectability)
    )


def priority_table() -> tuple[tuple[str, str, str, str], ...]:
    """Every combination and its band — the whole table, for snapshotting and for docs."""
    return tuple(
        (severity, occurrence, detectability, action_priority(severity, occurrence, detectability))
        for severity in SEVERITY_SCALE
        for occurrence in OCCURRENCE_SCALE
        for detectability in DETECTABILITY_SCALE
    )


def worst_band(bands: Sequence[str]) -> str | None:
    """The most urgent band present, for rolling several rows up to one component.

    `indeterminate` never wins: an unrated row is a gap to close, and letting it outrank a real
    `high` would bury the row that actually needs work. It is counted separately instead.
    """
    for band in (HIGH, MEDIUM, LOW):
        if band in bands:
            return band
    return INDETERMINATE if INDETERMINATE in bands else None
