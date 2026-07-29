"""Verdict-level fixture matrix: motivation branch completeness, overall_realization
leaf coverage, shortcut gaps, not-applicable, and the anti-false-gap witness — an
application-only requirement PASSES overall while the business diagnostic is none_observed."""

from __future__ import annotations

from src.application.viewpoints.trace_evaluator import evaluate_pattern
from src.application.viewpoints.trace_index import build_trace_graph_index
from src.application.viewpoints.trace_obligations import enumerate_row_obligations
from src.application.viewpoints.trace_realizers import eligible_realizer_types
from src.domain.relationships.relationship_reachability import DerivationBounds
from src.domain.viewpoints.viewpoint_trace_pattern_validation import expand_branch_edges
from src.domain.viewpoints.viewpoint_trace_patterns import (
    BranchesRef,
    DerivedReachabilityLeaf,
    DiagnosticEdge,
    InlineBranches,
    LayerMembershipEndpoint,
    NamedBranchEdge,
    NoneLeaf,
    RegistryEndpoint,
    StoredEdge,
    TracePattern,
    TracePatternSet,
)
from src.infrastructure.app_bootstrap import get_module_registry
from tests.application.viewpoints._fixtures import Store, connection, entity

_REF = frozenset({"archimate-realization", "archimate-influence", "archimate-association"})
_BOUNDS = DerivationBounds(max_hops=4, max_relationships=10_000, time_budget_seconds=2.0)

_MOTIVATION = TracePattern(
    name="motivation", applies_to=("goal", "outcome"),
    branches=InlineBranches((
        NamedBranchEdge("g2o", StoredEdge("archimate-realization", "incoming", "outcome")),
        NamedBranchEdge("o2r", StoredEdge("archimate-realization", "incoming", "requirement")),
    )),
    shortcuts=(DiagnosticEdge("archimate-influence", "incoming", "requirement", "shortcut"),),
    leaf=NoneLeaf(),
)
_OVERALL = TracePattern(
    name="overall_realization", applies_to=("goal", "outcome", "requirement"), branches=BranchesRef("motivation"),
    leaf=DerivedReachabilityLeaf("archimate-realization", RegistryEndpoint("permitted-realizers-of-requirement")),
)
_BUSINESS = TracePattern(
    name="business_coverage", applies_to=("goal", "outcome", "requirement"), branches=BranchesRef("motivation"),
    diagnostic=True, leaf=DerivedReachabilityLeaf("archimate-realization", LayerMembershipEndpoint("business")),
)
_APPLICATION = TracePattern(
    name="application_coverage", applies_to=("goal", "outcome", "requirement"), branches=BranchesRef("motivation"),
    diagnostic=True, leaf=DerivedReachabilityLeaf("archimate-realization", LayerMembershipEndpoint("application")),
)
_PATTERNS = TracePatternSet((_MOTIVATION, _OVERALL, _BUSINESS, _APPLICATION))
_TYPE = {"GOL": "goal", "OUT": "outcome", "REQ": "requirement", "APP": "application-component"}


def _e(eid: str):
    kind = _TYPE[eid.split("@")[0]]
    domain = {"application-component": "application"}.get(kind, "motivation")
    return entity(artifact_id=eid, artifact_type=kind, domain=domain, status="active")


def _rz(cid: str, source: str, target: str):
    return connection(artifact_id=cid, source=source, target=target, conn_type="archimate-realization")


def _index(entities, connections):
    store = Store(entities={e.artifact_id: e for e in entities}, connections=connections)
    return build_trace_graph_index(
        store, get_module_registry(), referenced_connection_types=_REF, requirement_type="requirement", bounds=_BOUNDS
    )


def _evaluate(entity_id, entity_type, pattern, index):
    edges = expand_branch_edges(pattern, _PATTERNS)
    obligations = enumerate_row_obligations(entity_id, entity_type, edges, pattern.shortcuts, index)
    expected_types = tuple(named.edge.endpoint_type for named in edges)
    eligible = eligible_realizer_types(get_module_registry())
    return evaluate_pattern(entity_type, pattern, obligations, expected_types, index, eligible)


def _complete_chain():
    # GOL ← OUT ← REQ, and APP realizes REQ (a real implementation realizer).
    entities = [_e("GOL@1"), _e("OUT@1"), _e("REQ@1"), _e("APP@1")]
    connections = [_rz("r1", "OUT@1", "GOL@1"), _rz("r2", "REQ@1", "OUT@1"), _rz("r3", "APP@1", "REQ@1")]
    return _index(entities, connections)


class TestMotivationBranchCompleteness:
    def test_complete_goal_passes(self) -> None:
        result = _evaluate("GOL@1", "goal", _MOTIVATION, _complete_chain())
        assert result.verdict == "pass"
        assert result.status_code == "ok"

    def test_goal_missing_outcome_is_incomplete_gap(self) -> None:
        result = _evaluate("GOL@1", "goal", _MOTIVATION, _index([_e("GOL@1")], []))
        assert result.verdict == "gap"
        assert result.status_code == "incomplete_branch"
        assert result.incomplete_branch_count == 1

    def test_outcome_without_requirement_is_gap(self) -> None:
        result = _evaluate("GOL@1", "goal", _MOTIVATION, _index(
            [_e("GOL@1"), _e("OUT@1")], [_rz("r1", "OUT@1", "GOL@1")]))
        assert result.verdict == "gap"
        assert result.status_code == "incomplete_branch"


class TestOverallRealization:
    def test_requirement_with_eligible_realizer_passes(self) -> None:
        index = _index([_e("REQ@1"), _e("APP@1")], [_rz("r", "APP@1", "REQ@1")])
        result = _evaluate("REQ@1", "requirement", _OVERALL, index)
        assert result.verdict == "pass"
        assert result.coverage.covered == 1 and result.coverage.applicable == 1

    def test_requirement_without_realizer_is_partial_gap(self) -> None:
        result = _evaluate("REQ@1", "requirement", _OVERALL, _index([_e("REQ@1")], []))
        assert result.verdict == "gap"
        assert result.status_code == "partial_branches"

    def test_complete_realized_goal_passes_overall(self) -> None:
        result = _evaluate("GOL@1", "goal", _OVERALL, _complete_chain())
        assert result.verdict == "pass"


class TestShortcutAndApplicability:
    def test_shortcut_is_a_gap_with_flag(self) -> None:
        index = _index([_e("GOL@1"), _e("REQ@1")], [
            connection(artifact_id="i", source="REQ@1", target="GOL@1", conn_type="archimate-influence")])
        result = _evaluate("GOL@1", "goal", _MOTIVATION, index)
        assert result.verdict == "gap"
        assert result.status_code == "shortcut"
        assert result.shortcut is True

    def test_motivation_not_applicable_to_requirement_row(self) -> None:
        result = _evaluate("REQ@1", "requirement", _MOTIVATION, _index([_e("REQ@1")], []))
        assert result.verdict == "not_applicable"
        assert result.status_code == "not_applicable"


class TestDiagnosticsNeverFalseGap:
    def test_application_only_requirement_passes_overall_but_business_is_none_observed(self) -> None:
        # The anti-false-gap witness: an application-realized requirement must PASS overall while the
        # business-layer diagnostic reads none_observed (verdict-neutral), never a gap.
        index = _index([_e("REQ@1"), _e("APP@1")], [_rz("r", "APP@1", "REQ@1")])
        overall = _evaluate("REQ@1", "requirement", _OVERALL, index)
        business = _evaluate("REQ@1", "requirement", _BUSINESS, index)
        application = _evaluate("REQ@1", "requirement", _APPLICATION, index)
        assert overall.verdict == "pass"
        assert business.role == "diagnostic" and business.observation == "none_observed"
        assert application.role == "diagnostic" and application.observation == "observed"
