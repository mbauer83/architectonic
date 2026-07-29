"""Branch enumeration: from a row entity, walk the pattern's DIRECT stored branch edges into
the canonical tagged obligation tuples.

Branch enumeration is over DIRECT stored edges only — derived relationships would collapse or
bypass the modeled branches this view must universally quantify over. Enumeration depends only
on the branch edges + shortcuts + the graph (NOT on the leaf), so it is computed ONCE per row
entity and reused by every pattern that shares those branches (all the ``{ref: motivation}``
patterns) — the leaf is applied afterwards.

The motivation chain is at most two levels (goal→outcome→requirement); the applicable suffix is
chosen by where the row's own type sits in the chain, so one enumerator serves goal rows,
outcome rows, and requirement rows without hardcoding connection names (they come from the
edges).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.viewpoints.trace_index import TraceGraphIndex
from src.domain.viewpoints.viewpoint_trace_patterns import DiagnosticEdge, NamedBranchEdge, StoredEdge
from src.domain.viewpoints.viewpoint_trace_result import (
    MissingOutcomeObligation,
    MissingRequirementObligation,
    ShortcutObligation,
    TerminalObligation,
)

MissingObligation = MissingRequirementObligation | MissingOutcomeObligation


@dataclass(frozen=True)
class RowObligations:
    terminals: tuple[TerminalObligation, ...]
    missing: tuple[MissingObligation, ...]
    shortcuts: tuple[ShortcutObligation, ...]
    ambiguous_link_ids: tuple[str, ...]  # association endpoints — diagnostic, verdict gap
    cycle: bool = False


def _neighbors(node: str, edge: StoredEdge | DiagnosticEdge, index: TraceGraphIndex) -> tuple[str, ...]:
    """Active entities of the edge's endpoint type reachable over ONE direct stored edge."""
    candidates = (
        index.sources(node, edge.connection) if edge.direction == "incoming"
        else index.targets(node, edge.connection)
    )
    return tuple(c for c in candidates if index.type_of.get(c) == edge.endpoint_type and index.is_active(c))


def enumerate_row_obligations(
    entity_id: str,
    entity_type: str,
    branch_edges: tuple[NamedBranchEdge, ...],
    shortcuts: tuple[DiagnosticEdge, ...],
    index: TraceGraphIndex,
) -> RowObligations:
    """Enumerate the row's obligations. The applicable branch suffix is chosen by the row's
    position in the chain: a chain-root row (e.g. goal) walks all edges; a row whose type is an
    intermediate endpoint (e.g. outcome) walks the edges after it; a terminal-type row is its own
    single obligation."""
    edges = tuple(named.edge for named in branch_edges)
    endpoint_types = [edge.endpoint_type for edge in edges]
    shortcut_obligations, ambiguous = _shortcuts(entity_id, shortcuts, index)

    if edges and entity_type == endpoint_types[-1]:
        # Terminal-type row (requirement): a single self-obligation, no branch walk.
        return RowObligations((TerminalObligation(entity_id, entity_id),), (), shortcut_obligations, ambiguous)
    if entity_type in endpoint_types:
        suffix = edges[endpoint_types.index(entity_type) + 1:]
        return _walk_from_intermediate(entity_id, suffix, index, shortcut_obligations, ambiguous)
    return _walk_from_root(entity_id, edges, index, shortcut_obligations, ambiguous)


def _shortcuts(
    entity_id: str, shortcuts: tuple[DiagnosticEdge, ...], index: TraceGraphIndex
) -> tuple[tuple[ShortcutObligation, ...], tuple[str, ...]]:
    shortcut_obligations: list[ShortcutObligation] = []
    ambiguous: list[str] = []
    for edge in shortcuts:
        for neighbor in _neighbors(entity_id, edge, index):
            if edge.status == "shortcut":
                shortcut_obligations.append(ShortcutObligation(entity_id, neighbor))
            else:
                ambiguous.append(neighbor)
    return tuple(shortcut_obligations), tuple(ambiguous)


def _walk_from_intermediate(
    outcome_id: str,
    suffix: tuple[StoredEdge, ...],
    index: TraceGraphIndex,
    shortcuts: tuple[ShortcutObligation, ...],
    ambiguous: tuple[str, ...],
) -> RowObligations:
    """Outcome row: expand its requirements directly. No requirements = an incomplete branch
    rooted at the outcome itself (never a vacuous pass — mirrors the goal 'missing' rule)."""
    if not suffix:
        return RowObligations((TerminalObligation(outcome_id, outcome_id),), (), shortcuts, ambiguous)
    requirements = _neighbors(outcome_id, suffix[0], index)
    if not requirements:
        missing: tuple[MissingObligation, ...] = (MissingRequirementObligation(outcome_id, outcome_id),)
        return RowObligations((), missing, shortcuts, ambiguous)
    terminals = tuple(TerminalObligation(outcome_id, req) for req in requirements)
    return RowObligations(terminals, (), shortcuts, ambiguous)


def _walk_from_root(
    goal_id: str,
    edges: tuple[StoredEdge, ...],
    index: TraceGraphIndex,
    shortcuts: tuple[ShortcutObligation, ...],
    ambiguous: tuple[str, ...],
) -> RowObligations:
    """Goal row: outcomes, then each outcome's requirements. A goal with no outcome AND no
    shortcut is a missing-outcome gap; an outcome with no requirement is a missing-requirement
    gap."""
    if not edges:
        return RowObligations((TerminalObligation(goal_id, goal_id),), (), shortcuts, ambiguous)
    outcomes = _neighbors(goal_id, edges[0], index)
    if not outcomes:
        missing_outcome: tuple[MissingObligation, ...] = () if shortcuts else (MissingOutcomeObligation(goal_id),)
        return RowObligations((), missing_outcome, shortcuts, ambiguous)
    if len(edges) == 1:
        reached = tuple(TerminalObligation(goal_id, outcome) for outcome in outcomes)
        return RowObligations(reached, (), shortcuts, ambiguous)
    terminals: list[TerminalObligation] = []
    missing: list[MissingObligation] = []
    requirement_edge = next(iter(edges[1:]))
    for outcome in outcomes:
        requirements = _neighbors(outcome, requirement_edge, index)
        if not requirements:
            missing.append(MissingRequirementObligation(goal_id, outcome))
        terminals.extend(TerminalObligation(goal_id, req, via_outcome_id=outcome) for req in requirements)
    return RowObligations(tuple(terminals), tuple(missing), shortcuts, ambiguous)
