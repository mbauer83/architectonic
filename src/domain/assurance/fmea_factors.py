"""The three factors a failure mode is rated on, and how a human judgement about one applies.

Severity and detectability are functions of the model, so they are computed. Occurrence is a claim
about how often something happens, and nothing in this repository measures a rate — complexity
correlates weakly with defect density, churn measures recent change, coverage measures testing, and
none of them is a frequency. So occurrence has exactly one source: a person asserting it with a
rationale. A failure mode without one has no occurrence, and the matrix shows that gap rather than
filling it.

**A judgement is keyed to the basis it was made against.** This is the rule VEX assessments already
follow, where an assessment is keyed to the exact component version it was made about and never
carries over to another. Transposed here: a factor judgement is keyed to a digest of the derived
inputs that were in front of the person at the time. When the model moves, the old judgement stops
applying and the derived value stands again — with the superseded revision retained and visible.

That is stronger than marking a stale value with a badge, and it is why no staleness flag exists: a
judgement made against a different consequence picture cannot continue to drive a priority. Value
comparison could never have served, because a loss may be swapped for another of equal severity, and
the value would compare equal while the basis changed underneath it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domain.assurance.assessment_scales import CONSEQUENCE_SEVERITY_SCALE, LIKELIHOOD_SCALE

SEVERITY = "severity"
OCCURRENCE = "occurrence"
DETECTABILITY = "detectability"

#: The three factors, in the order a reader meets them.
FMEA_FACTORS: tuple[str, ...] = (SEVERITY, OCCURRENCE, DETECTABILITY)

#: Only occurrence may be asserted from nothing. Severity and detectability are derived, and an
#: assertion about them is a correction to a computed value rather than a value of its own.
ASSERTED_ONLY_FACTORS: tuple[str, ...] = (OCCURRENCE,)

#: How detectable the failure is — higher means MORE detectable.
#:
#: Named `detectability` and pointing this way on purpose. Conventional FMEA "D" numbers rate worse
#: detection higher, so the two run opposite; the decision table inverts it exactly once, where it
#: is defined. Transcription errors live at that boundary, so the name states the direction it
#: carries rather than leaving a reader to infer it from a number.
DETECTABILITY_SCALE: tuple[str, ...] = ("very-low", "low", "moderate", "high", "very-high")

#: Severity rates the loss reached along the hazard chain, so it is the consequence scale — one
#: quantity, one scale, whether it is reached from a risk assessment or from a failure mode.
SEVERITY_SCALE: tuple[str, ...] = CONSEQUENCE_SEVERITY_SCALE

#: Occurrence is a frequency, which is what the existing likelihood scale rates. Reused rather than
#: restated: a second five-point frequency vocabulary would differ from this one eventually.
OCCURRENCE_SCALE: tuple[str, ...] = LIKELIHOOD_SCALE

FACTOR_SCALES: dict[str, tuple[str, ...]] = {
    SEVERITY: SEVERITY_SCALE,
    OCCURRENCE: OCCURRENCE_SCALE,
    DETECTABILITY: DETECTABILITY_SCALE,
}

#: Where an effective value came from. Reported alongside every value, because an unattributed
#: rating is one nobody can check.
BASIS_ASSERTED = "asserted"
BASIS_DERIVED = "derived"
BASIS_DERIVED_SUPERSEDING_AN_ASSESSMENT = "derived-superseding-an-assessment"
BASIS_ABSENT = "absent"


@dataclass(frozen=True)
class FactorAssessment:
    """One immutable factor judgement (persisted rows mirror this shape)."""

    node_id: str
    factor: str
    basis_digest: str
    revision: int
    value: str
    justification: str
    author: str
    created_at: str

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> "FactorAssessment":
        """Rebuild one judgement from a stored row.

        The rows mirror this shape, which is why every reader could write the reconstruction itself —
        and three did, byte-identically, in the application lens, the MCP tool and the REST route. A
        field added here reached none of them. It lives with the type it produces: the coercions are
        this type's tolerance for what a store returns, not each caller's guess at it.
        """
        return cls(
            node_id=str(row.get("node_id") or ""),
            factor=str(row.get("factor") or ""),
            basis_digest=str(row.get("basis_digest") or ""),
            revision=int(str(row.get("revision") or 0)),
            value=str(row.get("value") or ""),
            justification=str(row.get("justification") or ""),
            author=str(row.get("author") or ""),
            created_at=str(row.get("created_at") or ""),
        )


@dataclass(frozen=True)
class FactorValidationError:
    field: str
    message: str


@dataclass(frozen=True)
class EffectiveFactor:
    """A factor's value as a reader should see it, with where it came from."""

    factor: str
    value: str | None
    basis: str
    assessment: FactorAssessment | None = None
    """The judgement this value *is*, where a person made one that still applies.

    Carried for the same reason the superseded one is, and the more urgent of the two: this is the
    assessment currently moving the action-priority band, and `validate_factor_assessment` refuses
    to record one without a rationale precisely because "a band with no stated reason is exactly
    the number that gets argued about in a review". A rationale the product demands on the way in
    and cannot return on the way out is a rationale nobody can review."""
    superseded_assessment: FactorAssessment | None = None
    """An assessment that no longer applies because the basis moved. Retained and shown, so the
    reader can see a judgement was made and what it was made against."""


def validate_factor_assessment(
    factor: str, value: str, justification: str, author: str
) -> list[FactorValidationError]:
    """Reject a judgement that cannot be checked by whoever reads it later.

    A rationale and an author are required for every assertion, not only for the suppressing ones:
    a factor value moves a priority band, and a band with no stated reason is exactly the number
    that gets argued about in a review and cannot be defended.
    """
    errors: list[FactorValidationError] = []
    scale = FACTOR_SCALES.get(factor)
    if scale is None:
        errors.append(FactorValidationError(
            field="factor",
            message=f"unknown factor {factor!r}; valid: {', '.join(FMEA_FACTORS)}",
        ))
    elif value not in scale:
        errors.append(FactorValidationError(
            field="value",
            message=f"{value!r} is not a member of the {factor} scale; valid: {', '.join(scale)}",
        ))
    if not justification.strip():
        errors.append(FactorValidationError(
            field="justification",
            message="a factor assertion requires a rationale — it sets a priority band, so the "
                    "reason has to be readable without asking its author",
        ))
    if not author.strip():
        errors.append(FactorValidationError(field="author", message="author is required"))
    return errors


#: What stands in place of a digest when the picture a judgement would be made against could not be
#: assembled at all — the architecture model unreachable from the process, rather than reachable and
#: saying nothing about this element.
#:
#: Deliberately not a hash. `compute_basis_digest([])` is the legitimate digest of an element that
#: cites no facts in a basis that *was* assembled, so a marker equal to it would refuse a correct
#: judgement about an isolated element and admit an ungrounded one. Every real digest is 32 hex
#: characters; this is a word.
UNGROUNDED_BASIS = "ungrounded"


def is_grounded(basis_digest: str) -> bool:
    """Whether this digest names a picture a judgement can be held against.

    Two ways it does not, and they fail in opposite directions. An absent digest leaves nothing to
    retire the judgement, so it would apply forever. `UNGROUNDED_BASIS` says the picture was never
    assembled, so the judgement is born superseded and applies never. Both are refused at the write.
    """
    stripped = basis_digest.strip()
    return bool(stripped) and stripped != UNGROUNDED_BASIS


def compute_basis_digest(parts: Sequence[object]) -> str:
    """A stable digest of the derived inputs a judgement was made against.

    Canonical JSON so the same inputs always hash the same way regardless of how a caller built
    them: the digest is an identity, and one that varied with dict ordering would retire judgements
    at random.
    """
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def current_revision(assessments: Sequence[FactorAssessment]) -> FactorAssessment | None:
    """The latest revision among those given; retained superseded revisions never win."""
    return max(assessments, key=lambda a: a.revision, default=None)


def effective_factor(
    factor: str,
    *,
    assessments: Sequence[FactorAssessment],
    derived_value: str | None,
    current_basis_digest: str,
) -> EffectiveFactor:
    """What a reader should see for one factor, and on what basis.

    An assessment applies only while its basis still holds. Where it does not, the derived value
    stands again and the superseded judgement is carried alongside rather than discarded — the
    reader needs to know a person once decided this, and against what.
    """
    applicable = current_revision([a for a in assessments if a.basis_digest == current_basis_digest])
    if applicable is not None:
        return EffectiveFactor(
            factor=factor, value=applicable.value, basis=BASIS_ASSERTED, assessment=applicable,
        )
    superseded = current_revision(assessments)
    if derived_value is None:
        return EffectiveFactor(
            factor=factor, value=None, basis=BASIS_ABSENT, superseded_assessment=superseded,
        )
    if superseded is not None:
        return EffectiveFactor(
            factor=factor,
            value=derived_value,
            basis=BASIS_DERIVED_SUPERSEDING_AN_ASSESSMENT,
            superseded_assessment=superseded,
        )
    return EffectiveFactor(factor=factor, value=derived_value, basis=BASIS_DERIVED)
