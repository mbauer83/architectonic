"""Compose a row's enumerated obligations + the pattern's leaf into one ``PatternResult``.

The obligations (terminals + missing) come from ``trace_obligations`` — enumerated ONCE per row
and reused here across every pattern that shares those branches; only the leaf differs. A
``none`` leaf reports branch completeness only (the ``motivation`` verdict); a
``derived-reachability`` leaf tests each terminal requirement's realizer closure against the
target set (registry realizers = the authoritative ``overall_realization`` verdict; a layer =
a verdict-neutral diagnostic observation). Status is the single worst code by the fixed
precedence; the row verdict derives from it.
"""

from __future__ import annotations

from src.application.viewpoints.trace_index import TraceGraphIndex
from src.application.viewpoints.trace_obligations import RowObligations
from src.domain.viewpoints.viewpoint_trace_patterns import (
    DerivedReachabilityLeaf,
    LayerMembershipEndpoint,
    Leaf,
    RegistryEndpoint,
    TracePattern,
)
from src.domain.viewpoints.viewpoint_trace_result import (
    RESULT_CAP,
    AuthoritativePatternResult,
    Coverage,
    DiagnosticCode,
    DiagnosticPatternResult,
    MissingOutcomeObligation,
    Obligation,
    PatternResult,
    StatusCode,
    TerminalObligation,
    resolve_status,
    verdict_of,
)


def _leaf_covers(index: TraceGraphIndex, requirement_id: str, leaf: Leaf, eligible: frozenset[str]) -> bool:
    """Whether the requirement's realizer closure reaches the leaf's target. A ``none`` leaf is
    branch-completeness only, so every existing terminal counts as covered."""
    if not isinstance(leaf, DerivedReachabilityLeaf):
        return True
    realizers = index.realizers_of(requirement_id)
    endpoint = leaf.endpoint
    if isinstance(endpoint, RegistryEndpoint):
        return any(index.type_of.get(r) in eligible for r in realizers)
    return any(_in_layer(index, r, endpoint) for r in realizers)


def _in_layer(index: TraceGraphIndex, realizer_id: str, endpoint: LayerMembershipEndpoint) -> bool:
    if index.domain_of.get(realizer_id) != endpoint.domain:
        return False
    if endpoint.entity_class is None:
        return True
    return endpoint.entity_class in index.classes_by_type.get(index.type_of.get(realizer_id, ""), frozenset())


def _capped(items: tuple[object, ...]) -> tuple[tuple[object, ...], int]:
    return items[:RESULT_CAP], max(0, len(items) - RESULT_CAP)


def evaluate_pattern(
    entity_type: str,
    pattern: TracePattern,
    obligations: RowObligations,
    expected_types: tuple[str, ...],
    index: TraceGraphIndex,
    eligible: frozenset[str],
) -> PatternResult:
    if entity_type not in pattern.applies_to:
        if pattern.role == "diagnostic":
            return DiagnosticPatternResult(observation="not_applicable", last_satisfied_ids=())
        return AuthoritativePatternResult(
            verdict="not_applicable", status_code="not_applicable", coverage=Coverage(0, 0),
            incomplete_branch_count=0, failing_obligations=(), failing_overflow=0,
            last_satisfied_ids=(), missing_expected=(), shortcut=False,
        )
    covered = tuple(t for t in obligations.terminals if _leaf_covers(index, t.requirement_id, pattern.leaf, eligible))
    satisfied_ids, _ = _capped(tuple(t.requirement_id for t in covered))
    inferred = isinstance(pattern.leaf, DerivedReachabilityLeaf) and any(
        index.realized_only_potentially(terminal.requirement_id, eligible) for terminal in covered
    )
    if pattern.role == "diagnostic":
        observation = "observed" if covered else "none_observed"
        return DiagnosticPatternResult(observation=observation, last_satisfied_ids=tuple(satisfied_ids))  # type: ignore[arg-type]
    return _authoritative(
        obligations,
        covered,
        expected_types,
        tuple(satisfied_ids),  # type: ignore[arg-type]
        inferred=inferred,
    )


def _authoritative(
    obligations: RowObligations,
    covered: tuple[TerminalObligation, ...],
    expected_types: tuple[str, ...],
    satisfied_ids: tuple[str, ...],
    *,
    inferred: bool = False,
) -> AuthoritativePatternResult:
    terminals, shortcuts, missing = obligations.terminals, obligations.shortcuts, obligations.missing
    uncovered = tuple(t for t in terminals if t not in set(covered))
    status = _status(obligations, uncovered)
    failing_items: tuple[Obligation, ...] = missing + uncovered + shortcuts
    failing, overflow = _capped(failing_items)
    return AuthoritativePatternResult(
        verdict=verdict_of(status),
        status_code=status,
        coverage=Coverage(len(covered), len(terminals) + len(shortcuts)),
        incomplete_branch_count=len(missing),
        failing_obligations=tuple(failing),  # type: ignore[arg-type]
        failing_overflow=overflow,
        last_satisfied_ids=satisfied_ids,
        missing_expected=_missing_expected(missing, expected_types),
        shortcut=bool(shortcuts),
        diagnostic_code=_diagnostic_code(obligations, inferred=inferred),
    )


def _diagnostic_code(obligations: RowObligations, *, inferred: bool = False) -> DiagnosticCode | None:
    """The worst thing worth saying about how this verdict was reached.

    `potential_realization` ranks last: it is not a problem, it is a statement about evidence — the row
    passed because a grouping's members were substituted for it, which `PDR12` sanctions as potential.
    A cycle or an ambiguous link is a defect in the model and outranks it.
    """
    if obligations.cycle:
        return "cycle"
    if obligations.ambiguous_link_ids:
        return "ambiguous_link"
    return "potential_realization" if inferred else None


def _status(obligations: RowObligations, uncovered: tuple[TerminalObligation, ...]) -> StatusCode:
    codes: set[StatusCode] = set()
    if obligations.cycle:
        codes.add("cycle")
    if obligations.ambiguous_link_ids:
        codes.add("ambiguous_link")
    if obligations.missing:
        codes.add("incomplete_branch")
    if obligations.shortcuts:
        codes.add("shortcut")
    if uncovered:
        codes.add("partial_branches")
    if not (obligations.terminals or obligations.missing or obligations.shortcuts or obligations.ambiguous_link_ids):
        codes.add("no_trace")
    if not codes:
        codes.add("ok")
    return resolve_status(frozenset(codes))


def _missing_expected(missing: tuple[Obligation, ...], expected_types: tuple[str, ...]) -> tuple[str, ...]:
    """The declared next-node type descriptors for the absent branches, in chain order — the
    first endpoint type for a missing outcome, the last for a missing requirement."""
    if not missing or not expected_types:
        return ()
    descriptors: list[str] = []
    if any(isinstance(m, MissingOutcomeObligation) for m in missing) and expected_types[0] not in descriptors:
        descriptors.append(expected_types[0])
    if any(not isinstance(m, MissingOutcomeObligation) for m in missing) and expected_types[-1] not in descriptors:
        descriptors.append(expected_types[-1])
    return tuple(descriptors)
