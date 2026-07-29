"""Branch-enumeration fixture matrix: goal/outcome/requirement rows, missing-outcome
vs missing-requirement, shortcut vs ambiguous association, shared-requirement double counting,
and deprecated exclusion."""

from __future__ import annotations

from src.application.viewpoints.trace_index import build_trace_graph_index
from src.application.viewpoints.trace_obligations import enumerate_row_obligations
from src.domain.relationships.relationship_reachability import DerivationBounds
from src.domain.viewpoints.viewpoint_trace_patterns import DiagnosticEdge, NamedBranchEdge, StoredEdge
from src.domain.viewpoints.viewpoint_trace_result import (
    MissingOutcomeObligation,
    MissingRequirementObligation,
    ShortcutObligation,
    TerminalObligation,
)
from src.infrastructure.app_bootstrap import get_module_registry
from tests.application.viewpoints._fixtures import Store, connection, entity

_REF = frozenset({"archimate-realization", "archimate-influence", "archimate-association"})
_BOUNDS = DerivationBounds(max_hops=4, max_relationships=10_000, time_budget_seconds=2.0)

_BRANCHES = (
    NamedBranchEdge("goal_to_outcome", StoredEdge("archimate-realization", "incoming", "outcome")),
    NamedBranchEdge("outcome_to_requirement", StoredEdge("archimate-realization", "incoming", "requirement")),
)
_SHORTCUTS = (
    DiagnosticEdge("archimate-influence", "incoming", "requirement", "shortcut"),
    DiagnosticEdge("archimate-association", "incoming", "requirement", "ambiguous_link"),
)

_TYPE = {"GOL": "goal", "OUT": "outcome", "REQ": "requirement"}


def _e(eid: str, status: str = "active"):
    kind = _TYPE[eid.split("@")[0]]
    return entity(artifact_id=eid, artifact_type=kind, domain="motivation", status=status)


def _realizes(cid: str, source: str, target: str):
    return connection(artifact_id=cid, source=source, target=target, conn_type="archimate-realization")


def _index(entities, connections):
    store = Store(entities={e.artifact_id: e for e in entities}, connections=connections)
    return build_trace_graph_index(
        store, get_module_registry(), referenced_connection_types=_REF, requirement_type="requirement", bounds=_BOUNDS
    )


def _obligations(entity_id, entity_type, index):
    return enumerate_row_obligations(entity_id, entity_type, _BRANCHES, _SHORTCUTS, index)


class TestGoalRows:
    def test_zero_edge_pattern_uses_the_root_as_its_terminal(self) -> None:
        index = _index([_e("GOL@1")], [])
        obligations = enumerate_row_obligations("GOL@1", "goal", (), (), index)
        assert obligations.terminals == (TerminalObligation("GOL@1", "GOL@1"),)

    def test_one_edge_pattern_uses_reached_nodes_as_terminals(self) -> None:
        index = _index(
            [_e("GOL@1"), _e("OUT@1")],
            [_realizes("r1", "OUT@1", "GOL@1")],
        )
        branches = (_BRANCHES[0],)
        obligations = enumerate_row_obligations("GOL@1", "goal", branches, (), index)
        assert obligations.terminals == (TerminalObligation("GOL@1", "OUT@1"),)

    def test_goal_without_outcomes_or_shortcut_is_missing_outcome(self) -> None:
        index = _index([_e("GOL@1")], [])
        obligations = _obligations("GOL@1", "goal", index)
        assert obligations.missing == (MissingOutcomeObligation("GOL@1"),)
        assert obligations.terminals == ()

    def test_goal_with_shortcut_only_has_no_missing_outcome(self) -> None:
        index = _index(
            [_e("GOL@1"), _e("REQ@9")],
            [connection(artifact_id="I1", source="REQ@9", target="GOL@1", conn_type="archimate-influence")],
        )
        obligations = _obligations("GOL@1", "goal", index)
        assert obligations.missing == ()
        assert obligations.shortcuts == (ShortcutObligation("GOL@1", "REQ@9"),)

    def test_goal_outcome_without_requirements_is_missing_requirement(self) -> None:
        index = _index(
            [_e("GOL@1"), _e("OUT@1"), _e("OUT@2"), _e("REQ@1")],
            [_realizes("r1", "OUT@1", "GOL@1"), _realizes("r2", "OUT@2", "GOL@1"), _realizes("r3", "REQ@1", "OUT@1")],
        )
        obligations = _obligations("GOL@1", "goal", index)
        assert TerminalObligation("GOL@1", "REQ@1", via_outcome_id="OUT@1") in obligations.terminals
        assert MissingRequirementObligation("GOL@1", "OUT@2") in obligations.missing

    def test_shared_requirement_under_two_outcomes_is_two_obligations(self) -> None:
        index = _index(
            [_e("GOL@1"), _e("OUT@1"), _e("OUT@2"), _e("REQ@1")],
            [
                _realizes("r1", "OUT@1", "GOL@1"), _realizes("r2", "OUT@2", "GOL@1"),
                _realizes("r3", "REQ@1", "OUT@1"), _realizes("r4", "REQ@1", "OUT@2"),
            ],
        )
        terminals = set(_obligations("GOL@1", "goal", index).terminals)
        assert TerminalObligation("GOL@1", "REQ@1", via_outcome_id="OUT@1") in terminals
        assert TerminalObligation("GOL@1", "REQ@1", via_outcome_id="OUT@2") in terminals
        assert len(terminals) == 2

    def test_deprecated_outcome_is_excluded_from_branches(self) -> None:
        index = _index(
            [_e("GOL@1"), _e("OUT@1", status="deprecated")],
            [_realizes("r1", "OUT@1", "GOL@1")],
        )
        obligations = _obligations("GOL@1", "goal", index)
        # The only outcome is deprecated → excluded → goal reads as missing-outcome.
        assert obligations.missing == (MissingOutcomeObligation("GOL@1"),)


class TestOutcomeAndRequirementRows:
    def test_outcome_row_terminals_have_no_via(self) -> None:
        index = _index(
            [_e("OUT@1"), _e("REQ@1")], [_realizes("r1", "REQ@1", "OUT@1")],
        )
        obligations = _obligations("OUT@1", "outcome", index)
        assert obligations.terminals == (TerminalObligation("OUT@1", "REQ@1", via_outcome_id=None),)

    def test_outcome_without_requirements_is_incomplete(self) -> None:
        index = _index([_e("OUT@1")], [])
        obligations = _obligations("OUT@1", "outcome", index)
        assert obligations.missing == (MissingRequirementObligation("OUT@1", "OUT@1"),)

    def test_requirement_row_is_single_self_obligation(self) -> None:
        index = _index([_e("REQ@1")], [])
        obligations = _obligations("REQ@1", "requirement", index)
        assert obligations.terminals == (TerminalObligation("REQ@1", "REQ@1", via_outcome_id=None),)


class TestShortcutVsAmbiguous:
    def test_association_is_ambiguous_link_not_shortcut(self) -> None:
        index = _index(
            [_e("GOL@1"), _e("REQ@1"), _e("OUT@1")],
            [
                _realizes("r1", "OUT@1", "GOL@1"), _realizes("r2", "REQ@1", "OUT@1"),
                connection(artifact_id="a1", source="REQ@1", target="GOL@1", conn_type="archimate-association"),
            ],
        )
        obligations = _obligations("GOL@1", "goal", index)
        assert obligations.ambiguous_link_ids == ("REQ@1",)
        assert obligations.shortcuts == ()
