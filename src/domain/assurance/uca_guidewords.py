"""The STPA guidewords a control action is analysed against — defined once.

STPA asks, for each control action, how *providing or not providing* it could be unsafe. The
canonical set (Leveson & Thomas, *STPA Handbook*) is four:

  1. not providing it causes a hazard;
  2. providing it causes a hazard;
  3. it is provided too early, too late, or out of order;
  4. it is stopped too soon or applied too long — i.e. held for the wrong duration (continuous
     control actions only).

Guideword 2 is split here into two, because "providing causes a hazard" conflates two different
failures that need different constraints. A control action can be hazardous **because the context
is wrong** — the command itself is well-formed, but issuing it in this state is unsafe — or
**because the command is wrong** — issuing it is called for, but its content or parameters are not
what they should be. The first is answered by a guard on state; the second by validating the
command. Recording them in one column hides which of the two an analysis actually found.

This vocabulary was previously written out in six places, in three mutually inconsistent variants:
one authoring form offered `commission`/`omission`/`wrong-duration`, and since the store's
`uca_type` column has no enum constraint those values were accepted and then silently dropped by the
matrix, which only reads the columns it knows. Everything — the attribute-schema enum, the matrix
columns, the wizard, the authoring form, the store migration — now derives from here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UcaGuideword:
    """One way a control action can be unsafe."""

    slug: str
    """Persisted value of a UCA's `uca_type`."""
    label: str
    """Reader-facing column heading."""
    question: str
    """What the analyst is being asked, in the Handbook's terms."""
    continuous_only: bool = False
    """True for the guideword that only applies to a control action held over time."""


NOT_PROVIDED = UcaGuideword(
    slug="not-provided",
    label="Not provided",
    question="Does a hazard arise if the controller never issues this control action?",
)
PROVIDED_IN_UNSAFE_CONTEXT = UcaGuideword(
    slug="provided-in-unsafe-context",
    label="Provided in unsafe context",
    question=(
        "Does a hazard arise from issuing this control action in a state where it should not be "
        "issued, even though the command itself is well-formed?"
    ),
)
PROVIDED_INCORRECTLY = UcaGuideword(
    slug="provided-incorrectly",
    label="Provided incorrectly",
    question=(
        "Does a hazard arise from issuing this control action with the wrong content — wrong "
        "parameters, values, or payload — in a context where issuing it is otherwise correct?"
    ),
)
WRONG_TIMING = UcaGuideword(
    slug="wrong-timing",
    label="Wrong timing or order",
    question="Does a hazard arise if this control action is issued too early, too late, or out of order?",
)
WRONG_DURATION = UcaGuideword(
    slug="wrong-duration",
    label="Wrong duration",
    question=(
        "For a control action held over time: does a hazard arise if it stops before the process "
        "is in a safe state, or continues past the point it should have ended?"
    ),
    continuous_only=True,
)

#: Column order of the UCA matrix, and the order an analyst is walked through them.
UCA_GUIDEWORDS: tuple[UcaGuideword, ...] = (
    NOT_PROVIDED,
    PROVIDED_IN_UNSAFE_CONTEXT,
    PROVIDED_INCORRECTLY,
    WRONG_TIMING,
    WRONG_DURATION,
)

UCA_GUIDEWORD_SLUGS: tuple[str, ...] = tuple(g.slug for g in UCA_GUIDEWORDS)

#: Guideword values that predate this vocabulary. `provided` meant "provided when it should not be",
#: which is the unsafe-context reading; the incorrect-command reading had no home before, so nothing
#: maps to it. Kept so an existing analysis migrates without an analyst re-deciding anything.
LEGACY_GUIDEWORD_SLUGS: dict[str, str] = {
    "provided": PROVIDED_IN_UNSAFE_CONTEXT.slug,
    # `stopped-too-soon` named one of the two symptoms; the guideword covers both, and
    # `wrong-duration` is the parallel of `wrong-timing`.
    "stopped-too-soon": WRONG_DURATION.slug,
    # Variants an older authoring form offered, which named the act rather than its context.
    "commission": PROVIDED_IN_UNSAFE_CONTEXT.slug,
    "omission": NOT_PROVIDED.slug,
}


def canonical_guideword(slug: str | None) -> str | None:
    """Map a persisted `uca_type` to the current vocabulary; None stays None.

    An unrecognised value is returned unchanged — a UCA carrying a guideword this software does not
    know is still a finding, and silently rewriting it to something plausible would be worse than
    showing it as-is.
    """
    if slug is None:
        return None
    return LEGACY_GUIDEWORD_SLUGS.get(slug, slug)


def label_for(slug: str) -> str:
    """The reader-facing heading for a guideword slug, or the slug itself when unrecognised."""
    canonical = canonical_guideword(slug)
    return next((g.label for g in UCA_GUIDEWORDS if g.slug == canonical), slug)
