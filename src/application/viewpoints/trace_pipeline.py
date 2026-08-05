"""Post-projection trace phase: over an already-materialized row population, evaluate
every applicable pattern, compose the authoritative row verdict, drop not-applicable rows,
optionally keep only gaps, then sort gaps-first and page.

Filtering and sorting run AFTER evaluation because they consume verdicts — a gap beyond any
pre-trace page limit must still surface, so the population is materialized in full before the
limit is applied. Obligation enumeration is memoised per (entity, branch signature): all the
``{ref: motivation}`` patterns share one enumeration per row; only the leaf differs.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.viewpoints.trace_evaluator import evaluate_pattern
from src.application.viewpoints.trace_index import TraceGraphIndex
from src.application.viewpoints.trace_obligations import RowObligations, enumerate_row_obligations
from src.domain.viewpoints.viewpoint_trace_pattern_validation import expand_branch_edges, resolve_rollup
from src.domain.viewpoints.viewpoint_trace_patterns import (
    DiagnosticEdge,
    NamedBranchEdge,
    RollupEdge,
    TracePattern,
    TracePatternSet,
)
from src.domain.viewpoints.viewpoint_trace_result import AuthoritativePatternResult, PatternResult, Verdict

# Worst-first: a gap outranks a pass; not-applicable rows never reach the sort (filtered first).
_VERDICT_RANK: dict[Verdict, int] = {"gap": 0, "pass": 1, "not_applicable": 2}

#: The rollup is part of the key: it changes what enumeration walks, so two patterns that share
#: branches but differ in rollup are two enumerations, not one.
_MemoKey = tuple[str, tuple[NamedBranchEdge, ...], tuple[DiagnosticEdge, ...], RollupEdge | None]


@dataclass(frozen=True)
class TraceRow:
    entity_id: str
    entity_type: str
    name: str
    tier: str  # "enterprise" | "engagement"
    verdict: Verdict
    pattern_results: tuple[tuple[str, PatternResult], ...]  # (pattern name, result), declaration order


@dataclass(frozen=True)
class TraceTable:
    rows: tuple[TraceRow, ...]
    total_rows: int  # applicable rows before the page limit
    returned_rows: int
    truncated: bool  # the page limit dropped rows
    derived_truncated: bool  # the derived-realization pass hit its time budget


@dataclass(frozen=True)
class _PatternPlan:
    pattern: TracePattern
    branch_edges: tuple[NamedBranchEdge, ...]
    expected_types: tuple[str, ...]
    rollup: RollupEdge | None


def evaluate_trace_table(
    row_ids: tuple[str, ...],
    *,
    patterns: TracePatternSet,
    index: TraceGraphIndex,
    eligible: frozenset[str],
    gaps_only: bool = False,
    limit: int | None = None,
) -> TraceTable:
    plans = _plans(patterns)
    memo: dict[_MemoKey, RowObligations] = {}
    evaluated = [_row(entity_id, plans, index, eligible, memo) for entity_id in row_ids]
    applicable = [row for row in evaluated if row.verdict != "not_applicable"]
    filtered = [row for row in applicable if row.verdict == "gap"] if gaps_only else applicable
    ordered = sorted(filtered, key=lambda row: (_VERDICT_RANK[row.verdict], row.entity_type, row.name, row.entity_id))
    truncated = limit is not None and len(ordered) > limit
    paged = tuple(ordered[:limit] if limit is not None else ordered)
    return TraceTable(
        rows=paged, total_rows=len(applicable), returned_rows=len(paged),
        truncated=truncated, derived_truncated=index.derived_truncated,
    )


def _plans(patterns: TracePatternSet) -> tuple[_PatternPlan, ...]:
    return tuple(
        _PatternPlan(
            pattern=pattern,
            branch_edges=(edges := expand_branch_edges(pattern, patterns)),
            expected_types=tuple(named.edge.endpoint_type for named in edges),
            rollup=resolve_rollup(pattern, patterns),
        )
        for pattern in patterns.patterns
    )


def _row(
    entity_id: str,
    plans: tuple[_PatternPlan, ...],
    index: TraceGraphIndex,
    eligible: frozenset[str],
    memo: dict[_MemoKey, RowObligations],
) -> TraceRow:
    entity_type = index.type_of.get(entity_id, "")
    results: list[tuple[str, PatternResult]] = []
    for plan in plans:
        obligations = _obligations(entity_id, entity_type, plan, index, memo)
        result = evaluate_pattern(entity_type, plan.pattern, obligations, plan.expected_types, index, eligible)
        results.append((plan.pattern.name, result))
    tier = "enterprise" if entity_id in index.enterprise_ids else "engagement"
    return TraceRow(
        entity_id=entity_id, entity_type=entity_type, name=index.name_of.get(entity_id, entity_id),
        tier=tier, verdict=_row_verdict(results), pattern_results=tuple(results),
    )


def _obligations(
    entity_id: str, entity_type: str, plan: _PatternPlan, index: TraceGraphIndex, memo: dict[_MemoKey, RowObligations]
) -> RowObligations:
    key: _MemoKey = (entity_id, plan.branch_edges, plan.pattern.shortcuts, plan.rollup)
    cached = memo.get(key)
    if cached is None:
        cached = enumerate_row_obligations(
            entity_id, entity_type, plan.branch_edges, plan.pattern.shortcuts, index, plan.rollup
        )
        memo[key] = cached
    return cached


def _row_verdict(results: list[tuple[str, PatternResult]]) -> Verdict:
    """Worst authoritative verdict across the row's patterns (diagnostics are verdict-neutral).
    A row with no applicable authoritative pattern is not_applicable."""
    verdicts = [r.verdict for _, r in results if isinstance(r, AuthoritativePatternResult)]
    if "gap" in verdicts:
        return "gap"
    return "pass" if "pass" in verdicts else "not_applicable"
