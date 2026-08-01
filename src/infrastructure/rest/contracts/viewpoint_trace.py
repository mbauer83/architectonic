"""The coverage-trace table a viewpoint declaring ``trace_patterns`` carries on its execution.

Two discriminated unions, both already discriminated in the domain and neither of them optional to
model honestly. An **obligation** is tagged by ``kind`` because a shortcut is otherwise
indistinguishable from an outcome-less terminal, and a missing outcome from a missing requirement —
each arm carries a different pair of ids, and a flat model with four optional id fields would let a
client read ``requirement_id`` off an obligation that has none. A **pattern result** is tagged by
``role`` because a diagnostic observation is verdict-*neutral*: it is neither pass, gap, nor
not-applicable, and one shape carrying both would let it serialize as an authoritative verdict.

``pattern_results`` is a list of ``[name, result]`` pairs rather than a map: the order is the
definition's declaration order, and a JSON object would not preserve it.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from src.domain.viewpoints.viewpoint_trace_result import StatusCode, Verdict
from src.infrastructure.rest.contracts.wire_shape import Closed


class TerminalObligationResponse(Closed):
    """A terminal ``requirement`` obligation.

    ``via_outcome_id`` is the outcome a goal-rooted row reached the requirement through, and null on
    an outcome-rooted row — where there is no intermediate hop, not an unknown one.
    """

    kind: Literal["requirement"]
    root_id: str
    requirement_id: str
    via_outcome_id: str | None


class ShortcutObligationResponse(Closed):
    """A direct ``requirement —influence→ root`` branch: a gap, because it skips the outcome."""

    kind: Literal["shortcut"]
    root_id: str
    requirement_id: str


class MissingRequirementObligationResponse(Closed):
    """An outcome branch with no active realizing requirement — the expected node is absent."""

    kind: Literal["missing-requirement"]
    root_id: str
    outcome_id: str


class MissingOutcomeObligationResponse(Closed):
    """A goal with no outcome and no shortcut: zero expected branches, and a gap rather than a
    vacuous pass."""

    kind: Literal["missing-outcome"]
    root_id: str


TraceObligationResponse = Annotated[
    TerminalObligationResponse
    | ShortcutObligationResponse
    | MissingRequirementObligationResponse
    | MissingOutcomeObligationResponse,
    Field(discriminator="kind"),
]


class TraceCoverageResponse(Closed):
    """The terminal-obligation ratio for one row: how many of the applicable branches are covered."""

    covered: int
    applicable: int


class AuthoritativePatternResultResponse(Closed):
    """A pattern that decides the row's verdict.

    ``failing_obligations`` and ``last_satisfied_ids`` are capped server-side; ``failing_overflow``
    is how many were dropped, so a client never presents a truncated list as complete.
    """

    role: Literal["authoritative"]
    verdict: Verdict
    status_code: StatusCode
    coverage: TraceCoverageResponse
    incomplete_branch_count: int
    failing_obligations: list[TraceObligationResponse]
    failing_overflow: int
    last_satisfied_ids: list[str]
    #: Declared descriptors of the next-node types the trace expected and did not find.
    missing_expected: list[str]
    shortcut: bool
    diagnostic_code: Literal["cycle", "budget_aborted", "ambiguous_link"] | None


class DiagnosticPatternResultResponse(Closed):
    """A pattern that only observes. Its absence (``none_observed``) is verdict-neutral, and
    rendering it as a pass or a gap would report a finding the evaluation did not make."""

    role: Literal["diagnostic"]
    observation: Literal["observed", "none_observed", "not_applicable"]
    last_satisfied_ids: list[str]


PatternResultResponse = Annotated[
    AuthoritativePatternResultResponse | DiagnosticPatternResultResponse,
    Field(discriminator="role"),
]


class TraceRowResponse(Closed):
    """One traced entity: its identity, its composed verdict, and each pattern's result.

    ``pattern_results`` pairs a pattern's declared name with its result, in declaration order.
    """

    entity_id: str
    entity_type: str
    name: str
    tier: str
    verdict: Verdict
    pattern_results: list[tuple[str, PatternResultResponse]]


class TraceTableResponse(Closed):
    """The branch-complete coverage table, already gaps-filtered, sorted and paged.

    ``total_rows`` counts the applicable population *before* the page limit, so a gap beyond the
    page still registers in the header rather than disappearing with the rows.
    ``derived_truncated`` reports separately that the derived-realization pass hit its time budget:
    the rows shown are sound, but absence is no longer evidence of a gap.
    """

    rows: list[TraceRowResponse]
    total_rows: int
    returned_rows: int
    truncated: bool
    derived_truncated: bool
