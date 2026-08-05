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
from src.domain.viewpoints.viewpoint_trace_patterns import (
    DiagnosticEdge,
    NamedBranchEdge,
    RollupEdge,
    StoredEdge,
)
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
    rollup: RollupEdge | None = None,
) -> RowObligations:
    """Enumerate the row's obligations. The applicable branch suffix is chosen by the row's
    position in the chain: a chain-root row (e.g. goal) walks all edges; a row whose type is an
    intermediate endpoint (e.g. outcome) walks the edges after it; a terminal-type row is its own
    single obligation.

    With a ``rollup`` declared, a chain-root row that aggregates same-type constituents composes
    from them instead of bearing a missing-* obligation of its own — see :class:`RollupEdge`."""
    edges = tuple(named.edge for named in branch_edges)
    endpoint_types = [edge.endpoint_type for edge in edges]
    shortcut_obligations, ambiguous = _shortcuts(entity_id, shortcuts, index)

    if rollup is not None:
        return _walk_with_rollup(
            entity_id, entity_type, edges, endpoint_types, rollup, index, shortcut_obligations, ambiguous
        )
    return _walk_own(entity_id, entity_type, edges, endpoint_types, index, shortcut_obligations, ambiguous)


def _walk_own(
    entity_id: str,
    entity_type: str,
    edges: tuple[StoredEdge, ...],
    endpoint_types: list[str],
    index: TraceGraphIndex,
    shortcuts: tuple[ShortcutObligation, ...],
    ambiguous: tuple[str, ...],
) -> RowObligations:
    """The row's own obligations, by where its type sits in the chain. No composition."""
    if edges and entity_type == endpoint_types[-1]:
        # Terminal-type row (requirement): a single self-obligation, no branch walk.
        return RowObligations((TerminalObligation(entity_id, entity_id),), (), shortcuts, ambiguous)
    if entity_type in endpoint_types:
        suffix = edges[endpoint_types.index(entity_type) + 1:]
        return _walk_from_intermediate(entity_id, suffix, index, shortcuts, ambiguous)
    return _walk_from_root(entity_id, edges, index, shortcuts, ambiguous)


def _asks_about_itself(obligation: object, entity_id: str) -> bool:
    """Whether this obligation's subject is the row itself, rather than something it branches to.

    Those are the ones an aggregate hands to its constituents: "is anything realizing *me*"
    (a terminal self-obligation), "have I any outcome at all", "has my own outcome any requirement".
    A branch to a node that genuinely exists stays the aggregate's own to satisfy.
    """
    match obligation:
        case MissingOutcomeObligation(root_id=root):
            return root == entity_id
        case MissingRequirementObligation(root_id=root, outcome_id=outcome):
            return root == entity_id and outcome == entity_id
        case TerminalObligation(root_id=root, requirement_id=requirement):
            return root == entity_id and requirement == entity_id
        case _:
            return False


def _walk_with_rollup(
    entity_id: str,
    entity_type: str,
    edges: tuple[StoredEdge, ...],
    endpoint_types: list[str],
    rollup: RollupEdge,
    index: TraceGraphIndex,
    shortcuts: tuple[ShortcutObligation, ...],
    ambiguous: tuple[str, ...],
    seen: frozenset[str] = frozenset(),
) -> RowObligations:
    """A row that may aggregate peers of its own type: its branches, minus itself, plus theirs.

    One rule at every level: **an aggregate drops the obligation that asks about itself** — the goal
    with no outcome of its own, the outcome with no requirement of its own, the requirement asking to
    be realized — because its constituents answer it. Branches to nodes that do exist stay its own, so
    an apex that is also realized directly must still have that outcome refined: a direct edge onto an
    aggregate can only add an obligation, never buy a greener row.

    Nothing is retagged on the way up. An obligation keeps the constituent it belongs to as its root,
    so a report names where the gap actually is instead of blaming the aggregate for it.
    """
    own = _walk_own(entity_id, entity_type, edges, endpoint_types, index, shortcuts, ambiguous)
    constituents = tuple(c for c in _neighbors(entity_id, rollup.as_stored(entity_type), index) if c != entity_id)
    if not constituents:
        return own

    revisited = any(c in seen for c in constituents)
    descended = seen | {entity_id}
    parts = [
        _walk_with_rollup(
            constituent, entity_type, edges, endpoint_types, rollup, index, (), (), descended
        )
        for constituent in constituents
        if constituent not in seen
    ]
    return RowObligations(
        terminals=tuple(t for t in own.terminals if not _asks_about_itself(t, entity_id))
        + tuple(t for part in parts for t in part.terminals),
        missing=tuple(m for m in own.missing if not _asks_about_itself(m, entity_id))
        + tuple(m for part in parts for m in part.missing),
        shortcuts=own.shortcuts + tuple(s for part in parts for s in part.shortcuts),
        ambiguous_link_ids=own.ambiguous_link_ids + tuple(a for part in parts for a in part.ambiguous_link_ids),
        cycle=own.cycle or revisited or any(part.cycle for part in parts),
    )


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
