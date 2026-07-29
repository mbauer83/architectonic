"""Result semantics for branch-complete trace evaluation: the canonical tagged obligation
tuples, the closed status registry with fixed precedence and verdict mapping, and the
discriminated ``PatternResult`` union.

Obligations are frozen (hashable) value objects: duplicate traversal paths to the same tuple
collapse in a set, distinct tuples never collapse — a requirement realizing two outcomes is
two obligations even when one leaf realizer satisfies both. The union is discriminated by
``role`` because diagnostic *absence* is neither pass, gap, nor not-applicable and must never
serialize as an authoritative verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Verdict = Literal["pass", "gap", "not_applicable"]
Observation = Literal["observed", "none_observed", "not_applicable"]
DiagnosticCode = Literal["cycle", "budget_aborted", "ambiguous_link"]

StatusCode = Literal[
    "ok", "shortcut", "incomplete_branch", "partial_branches",
    "no_trace", "ambiguous_link", "cycle", "observed", "none_observed", "not_applicable",
]

# Worst-first precedence for authoritative rows: when several statuses apply to one
# row, the earliest in this tuple wins.
AUTHORITATIVE_STATUS_PRECEDENCE: tuple[StatusCode, ...] = (
    "cycle", "ambiguous_link", "incomplete_branch", "shortcut", "partial_branches", "no_trace", "ok",
)

_GAP_STATUSES: frozenset[str] = frozenset(
    {"shortcut", "incomplete_branch", "partial_branches", "no_trace", "ambiguous_link", "cycle"}
)

RESULT_CAP = 5  # failing_obligations and last_satisfied_ids are bounded to this, with an overflow count


def resolve_status(codes: frozenset[StatusCode]) -> StatusCode:
    """The single authoritative status for a row/cell: the worst present by precedence, or
    ``not_applicable`` when nothing applies (an out-of-scope row)."""
    for code in AUTHORITATIVE_STATUS_PRECEDENCE:
        if code in codes:
            return code
    return "not_applicable"


def verdict_of(status: StatusCode) -> Verdict:
    """Map an authoritative status to its verdict. Diagnostic observations are never passed
    here — they are verdict-neutral and carry no row verdict."""
    if status == "ok":
        return "pass"
    if status in _GAP_STATUSES:
        return "gap"
    return "not_applicable"


# --- Tagged obligation tuples ----------------------------------------------------------


@dataclass(frozen=True)
class TerminalObligation:
    """A terminal ``requirement`` obligation. ``via_outcome_id`` is set for a goal-rooted row
    (``root``→outcome→requirement) and ``None`` for an outcome-rooted row."""

    root_id: str
    requirement_id: str
    via_outcome_id: str | None = None
    kind: Literal["requirement"] = "requirement"

    def canonical(self) -> tuple[str, ...]:
        if self.via_outcome_id is None:
            return (self.kind, self.root_id, self.requirement_id)
        return (self.kind, self.root_id, self.via_outcome_id, self.requirement_id)


@dataclass(frozen=True)
class ShortcutObligation:
    """A direct ``requirement —influence→ root`` shortcut branch (status ``shortcut``, gap)."""

    root_id: str
    requirement_id: str
    kind: Literal["shortcut"] = "shortcut"

    def canonical(self) -> tuple[str, ...]:
        return (self.kind, self.root_id, self.requirement_id)


@dataclass(frozen=True)
class MissingRequirementObligation:
    """An outcome branch with no active realizing requirement (the outcome exists, the next
    expected node does not) — a gap the existing-node denominator cannot otherwise see."""

    root_id: str
    outcome_id: str
    kind: Literal["missing-requirement"] = "missing-requirement"

    def canonical(self) -> tuple[str, ...]:
        return (self.kind, self.root_id, self.outcome_id)


@dataclass(frozen=True)
class MissingOutcomeObligation:
    """A goal with no outcome and no shortcut — zero expected branches, a gap, never vacuous."""

    root_id: str
    kind: Literal["missing-outcome"] = "missing-outcome"

    def canonical(self) -> tuple[str, ...]:
        return (self.kind, self.root_id)


Obligation = TerminalObligation | ShortcutObligation | MissingRequirementObligation | MissingOutcomeObligation

_MISSING_OBLIGATIONS = (MissingRequirementObligation, MissingOutcomeObligation)


def is_missing_obligation(obligation: Obligation) -> bool:
    """A missing-* obligation stands for an ABSENT expected node; its presence is what makes a
    row an ``incomplete_branch`` gap independent of terminal coverage."""
    return isinstance(obligation, _MISSING_OBLIGATIONS)


# --- Result DTO (discriminated union) --------------------------------------------------


@dataclass(frozen=True)
class Coverage:
    """Terminal-obligation ratio for a row/cell (over ``requirement``/``shortcut`` tuples)."""

    covered: int
    applicable: int


@dataclass(frozen=True)
class AuthoritativePatternResult:
    verdict: Verdict
    status_code: StatusCode
    coverage: Coverage
    incomplete_branch_count: int
    failing_obligations: tuple[Obligation, ...]  # capped at RESULT_CAP
    failing_overflow: int
    last_satisfied_ids: tuple[str, ...]  # capped at RESULT_CAP
    missing_expected: tuple[str, ...]  # declared expected next-node type descriptors
    shortcut: bool
    diagnostic_code: DiagnosticCode | None = None
    role: Literal["authoritative"] = "authoritative"


@dataclass(frozen=True)
class DiagnosticPatternResult:
    observation: Observation
    last_satisfied_ids: tuple[str, ...]  # capped at RESULT_CAP
    role: Literal["diagnostic"] = "diagnostic"

    @property
    def status_code(self) -> Observation:
        # For a diagnostic pattern the status IS the observation (never a verdict status).
        return self.observation


PatternResult = AuthoritativePatternResult | DiagnosticPatternResult
