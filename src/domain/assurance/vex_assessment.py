"""Contextual VEX assessments: key, revisions, and suppression semantics.

Key: ``(anchor_entity_id, canonical_component_id_incl_version,
canonical_vulnerability_id)`` — run-independent. An assessment applies exactly
when a run contains that component/version/vulnerability finding; it never
carries over to any other component version.

Assessments are immutable revisions; the current revision per key is the
latest valid one (superseded revisions are retained). Only ``not_affected``
and ``fixed`` suppress an open finding, and both require a justification.
Visibility is evaluated BEFORE suppression by the caller: a revision the
caller cannot see must never be passed in here to suppress a finding the
caller can see.

The four values are OpenVEX's ``status`` vocabulary verbatim, and the field is
named ``vex_status`` after it. The ``vex_`` prefix is what keeps the word
unambiguous: a bare ``status`` would collide with the status every assurance
node carries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

VexStatus = Literal["affected", "not_affected", "fixed", "under_investigation"]

VALID_VEX_STATUSES: frozenset[str] = frozenset({
    "affected", "not_affected", "fixed", "under_investigation",
})

SUPPRESSING_VEX_STATUSES: frozenset[str] = frozenset({"not_affected", "fixed"})


@dataclass(frozen=True)
class VexAssessmentKey:
    anchor_entity_id: str
    canonical_component_id: str  # includes the exact version
    canonical_vulnerability_id: str


@dataclass(frozen=True)
class VexRevision:
    """One immutable assessment revision (persisted rows mirror this shape)."""

    key: VexAssessmentKey
    revision: int
    vex_status: str
    justification: str
    author: str
    created_at: str


@dataclass(frozen=True)
class VexValidationError:
    field: str
    message: str


def validate_assessment(vex_status: str, justification: str, author: str) -> list[VexValidationError]:
    errors: list[VexValidationError] = []
    if vex_status not in VALID_VEX_STATUSES:
        errors.append(VexValidationError(
            field="vex_status",
            message=f"unknown vex_status {vex_status!r}; valid: {', '.join(sorted(VALID_VEX_STATUSES))}",
        ))
    if vex_status in SUPPRESSING_VEX_STATUSES and not justification.strip():
        errors.append(VexValidationError(
            field="justification",
            message=f"vex_status {vex_status!r} suppresses a finding and requires a justification",
        ))
    if not author.strip():
        errors.append(VexValidationError(field="author", message="author is required"))
    return errors


def current_revision(revisions: Sequence[VexRevision]) -> VexRevision | None:
    """Latest-valid precedence: the highest revision number wins; retained
    superseded revisions never influence the outcome."""
    return max(revisions, key=lambda r: r.revision, default=None)


def suppresses_finding(revision: VexRevision | None) -> bool:
    """Whether the CURRENT visible revision suppresses the open finding."""
    return revision is not None and revision.vex_status in SUPPRESSING_VEX_STATUSES
