"""The guidewords a component's function is analysed against — defined once.

Failure-mode analysis asks, for each component or function, *how could this fail to perform as
intended*. Enumerating that freehand produces inconsistent worksheets, so the question is asked
against a fixed set of guidewords. These five are the set SAE J1739 and the AIAG-VDA handbook
use, and they cover the ways a function can deviate: not at all, too little, too much,
unreliably, and when it should not.

They are deliberately parallel to the five STPA guidewords in `uca_guidewords.py`, which ask the
same shape of question about a control action rather than a component. Reading them side by side
is how the two methods become learnable together — and it is worth being clear about what that
parallel does *not* mean: a component guideword finds a failure, and a control-action guideword
finds a flaw in coordination where nothing failed. Neither set covers the other's ground.

Written here rather than in the schema, the matrix columns and the authoring form separately,
because the UCA vocabulary was once written out in six places in three mutually inconsistent
variants — and since the store's type column has no enum constraint, the divergent values were
accepted and then silently dropped by the surfaces that did not recognise them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureGuideword:
    """One way a component or function can fail to perform as intended."""

    slug: str
    """Persisted value of a failure mode's `failure_type`."""
    label: str
    """Reader-facing column heading."""
    question: str
    """What the analyst is being asked."""


NO_FUNCTION = FailureGuideword(
    slug="no-function",
    label="No function",
    question="Does it fail to perform at all?",
)
PARTIAL_FUNCTION = FailureGuideword(
    slug="partial-function",
    label="Partial or degraded function",
    question="Does it perform below what is required?",
)
EXCESSIVE_FUNCTION = FailureGuideword(
    slug="excessive-function",
    label="Excessive function",
    question="Does it perform beyond what is required?",
)
INTERMITTENT_FUNCTION = FailureGuideword(
    slug="intermittent-function",
    label="Intermittent function",
    question="Does it perform unreliably over time?",
)
UNINTENDED_FUNCTION = FailureGuideword(
    slug="unintended-function",
    label="Unintended function",
    question="Does it perform when it should not?",
)

#: Column order of the failure-mode matrix, and the order an analyst is walked through them.
FAILURE_GUIDEWORDS: tuple[FailureGuideword, ...] = (
    NO_FUNCTION,
    PARTIAL_FUNCTION,
    EXCESSIVE_FUNCTION,
    INTERMITTENT_FUNCTION,
    UNINTENDED_FUNCTION,
)

FAILURE_GUIDEWORD_SLUGS: tuple[str, ...] = tuple(g.slug for g in FAILURE_GUIDEWORDS)


def label_for(slug: str) -> str:
    """The reader-facing heading for a guideword slug, or the slug itself when unrecognised.

    An unrecognised value is shown as it stands rather than rewritten to something plausible: a
    failure mode carrying a guideword this software does not know is still a finding.
    """
    return next((g.label for g in FAILURE_GUIDEWORDS if g.slug == slug), slug)


# ── What a matrix cell holds ──────────────────────────────────────────────────
#
# One cell is one (element, guideword) pair. Three states, because two of them would leave an
# empty cell meaning either "nobody has looked at this" or "someone looked and there is nothing
# here" — and an unstarted analysis would then be indistinguishable from a complete one.
#
# `not-credible` is deliberately NOT the existing `binding_status: out-of-scope`, which means
# "outside the analysis boundary". A cell judged not credible is *inside* the boundary and was
# examined. Folding the two together would lose the difference between a decision and an
# omission, so they are named apart.
#
# Dismissing has to be as cheap as filling in, or analysts write filler to make the grid look
# finished. It costs one action plus a reason, and it counts as coverage.

#: No one has examined this cell yet. Never persisted — it is the absence of a failure mode, and
#: writing a node to say nothing has happened would make coverage depend on bookkeeping.
UNTOUCHED = "untouched"

#: Examined, and this component cannot fail this way in a way that matters here. Persisted, with
#: who decided and why, because it is a judgement someone is accountable for.
NOT_CREDIBLE = "not-credible"

#: A real failure mode, carrying its effect, controls and factors.
RECORDED = "recorded"

#: Vocabulary of the `assessment_state` attribute.
ASSESSMENT_STATES: tuple[str, ...] = (UNTOUCHED, NOT_CREDIBLE, RECORDED)

#: The states a stored failure mode can be in. `untouched` is excluded by construction.
PERSISTED_ASSESSMENT_STATES: tuple[str, ...] = (NOT_CREDIBLE, RECORDED)

#: States that count as answered when measuring coverage. A dismissal is an answer.
ANSWERED_ASSESSMENT_STATES: tuple[str, ...] = (NOT_CREDIBLE, RECORDED)
