"""Neighbor traversal contract: deterministic size-budget truncation with
frontier ids, whole-request time-budget abort, per-hop exposure omission
(no pass-through over hidden nodes), cycles, self-loops, and multiedges."""

from __future__ import annotations

from typing import Any

import pytest

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.application.assurance_neighbors import (
    NeighborBudgets,
    NeighborhoodGraph,
    NeighborTimeBudgetExceeded,
    traverse_neighbors,
)


class GraphStore:
    """Minimal NeighborGraphReads fake over in-memory node/edge lists."""

    def __init__(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        self._nodes = nodes
        self._edges = edges

    def list_nodes(self) -> list[dict[str, object]]:
        return list(self._nodes)

    def list_edges(
        self,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
    ) -> list[dict[str, object]]:
        return [
            e for e in self._edges
            if (source_id is None or e["source_id"] == source_id)
            and (target_id is None or e["target_id"] == target_id)
        ]


def _node(node_id: str, tlp: str = "TLP:WHITE") -> dict[str, Any]:
    return {"node_id": node_id, "name": f"Name {node_id}", "node_type": "hazard", "tlp": tlp}


def _edge(edge_id: str, source: str, target: str, conn_type: str = "leads-to") -> dict[str, Any]:
    return {"edge_id": edge_id, "source_id": source, "target_id": target, "conn_type": conn_type}


def _budgets(max_hops: int = 1, max_nodes: int = 150, max_edges: int = 300) -> NeighborBudgets:
    return NeighborBudgets(
        max_hops=max_hops, max_nodes=max_nodes, max_edges=max_edges, time_budget_seconds=5.0,
    )


def _traverse(
    root: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    budgets: NeighborBudgets | None = None,
    ceiling: str = "TLP:RED",
) -> NeighborhoodGraph | None:
    return traverse_neighbors(
        root,
        store=GraphStore(nodes, edges),
        policy=AssuranceExposurePolicy(ceiling, True),
        budgets=budgets or _budgets(),
    )


class TestBasicShape:
    def test_one_hop_neighborhood_with_annotations(self) -> None:
        result = _traverse(
            "A",
            [_node("A"), _node("B"), _node("C")],
            [_edge("E1", "A", "B"), _edge("E2", "C", "A")],
        )
        assert result is not None
        assert [(n["node_id"], n["hop"], n["is_root"]) for n in result.nodes] == [
            ("A", 0, True), ("B", 1, False), ("C", 1, False),
        ]
        by_id = {e["edge_id"]: e for e in result.edges}
        assert by_id["E1"]["direction"] == "outgoing"
        assert by_id["E2"]["direction"] == "incoming"
        assert all(e["hop"] == 1 for e in result.edges)
        assert by_id["E1"]["target_name"] == "Name B"  # enriched
        assert result.truncated is False
        assert result.frontier_node_ids == []

    def test_max_hops_limits_depth(self) -> None:
        chain = [_edge("E1", "A", "B"), _edge("E2", "B", "C")]
        nodes = [_node("A"), _node("B"), _node("C")]
        one = _traverse("A", nodes, chain, budgets=_budgets(max_hops=1))
        two = _traverse("A", nodes, chain, budgets=_budgets(max_hops=2))
        assert one is not None and two is not None
        assert {n["node_id"] for n in one.nodes} == {"A", "B"}
        assert {n["node_id"] for n in two.nodes} == {"A", "B", "C"}
        assert {n["node_id"]: n["hop"] for n in two.nodes}["C"] == 2

    def test_absent_and_above_ceiling_roots_are_indistinguishable(self) -> None:
        nodes = [_node("A"), _node("R", tlp="TLP:RED")]
        absent = _traverse("MISSING", nodes, [], ceiling="TLP:AMBER")
        hidden = _traverse("R", nodes, [], ceiling="TLP:AMBER")
        assert absent is None and hidden is None


class TestGraphShapes:
    def test_cycle_terminates_and_records_shortest_hop(self) -> None:
        edges = [_edge("E1", "A", "B"), _edge("E2", "B", "C"), _edge("E3", "C", "A")]
        result = _traverse("A", [_node("A"), _node("B"), _node("C")], edges,
                           budgets=_budgets(max_hops=4))
        assert result is not None
        hops = {n["node_id"]: n["hop"] for n in result.nodes}
        assert hops == {"A": 0, "B": 1, "C": 1}  # C reached backwards via E3
        assert {e["edge_id"] for e in result.edges} == {"E1", "E2", "E3"}

    def test_self_loop_appears_once_with_self_direction(self) -> None:
        result = _traverse("A", [_node("A")], [_edge("E1", "A", "A")])
        assert result is not None
        assert [n["node_id"] for n in result.nodes] == ["A"]
        assert [(e["edge_id"], e["direction"]) for e in result.edges] == [("E1", "self")]

    def test_multiedges_are_distinct(self) -> None:
        edges = [_edge("E1", "A", "B"), _edge("E2", "A", "B", conn_type="explains")]
        result = _traverse("A", [_node("A"), _node("B")], edges)
        assert result is not None
        assert {e["edge_id"] for e in result.edges} == {"E1", "E2"}


class TestExposure:
    def test_hidden_node_is_never_a_pass_through_hop(self) -> None:
        nodes = [_node("A"), _node("H", tlp="TLP:RED"), _node("C")]
        edges = [_edge("E1", "A", "H"), _edge("E2", "H", "C")]
        result = _traverse("A", nodes, edges, budgets=_budgets(max_hops=4), ceiling="TLP:AMBER")
        assert result is not None
        assert {n["node_id"] for n in result.nodes} == {"A"}
        assert result.edges == []
        assert result.truncated is False  # policy omission is silent, not truncation


class TestSizeBudgets:
    def test_node_budget_truncates_with_frontier_and_omits_the_edge(self) -> None:
        nodes = [_node(i) for i in ("A", "B", "C")]
        edges = [_edge("E1", "A", "B"), _edge("E2", "A", "C")]
        result = _traverse("A", nodes, edges, budgets=_budgets(max_nodes=2))
        assert result is not None
        assert {n["node_id"] for n in result.nodes} == {"A", "B"}  # deterministic: E1 sorts first
        assert {e["edge_id"] for e in result.edges} == {"E1"}  # E2 would dangle → omitted
        assert result.truncated is True
        assert result.frontier_node_ids == ["A"]

    def test_edge_budget_truncates_with_frontier(self) -> None:
        nodes = [_node(i) for i in ("A", "B", "C")]
        edges = [_edge("E1", "A", "B"), _edge("E2", "A", "C")]
        result = _traverse("A", nodes, edges, budgets=_budgets(max_edges=1))
        assert result is not None
        assert {e["edge_id"] for e in result.edges} == {"E1"}
        assert {n["node_id"] for n in result.nodes} == {"A", "B"}  # C's discovering edge was cut
        assert result.truncated is True
        assert result.frontier_node_ids == ["A"]

    def test_within_budget_graph_is_not_truncated(self) -> None:
        result = _traverse("A", [_node("A"), _node("B")], [_edge("E1", "A", "B")],
                           budgets=_budgets(max_nodes=2, max_edges=1))
        assert result is not None
        assert result.truncated is False
        assert result.frontier_node_ids == []


class TestDeterminism:
    def test_store_ordering_does_not_change_the_result(self) -> None:
        nodes = [_node(i) for i in ("A", "B", "C", "D")]
        edges = [
            _edge("E1", "A", "B"), _edge("E2", "A", "C"),
            _edge("E3", "A", "D"), _edge("E4", "C", "D"),
        ]
        budgets = _budgets(max_hops=2, max_nodes=3, max_edges=3)
        forward = _traverse("A", nodes, edges, budgets=budgets)
        backward = _traverse("A", list(reversed(nodes)), list(reversed(edges)), budgets=budgets)
        assert forward == backward
        assert forward is not None and forward.truncated is True


class TestTimeBudget:
    def test_exceeding_the_time_budget_aborts_the_whole_request(self) -> None:
        nodes = [_node(i) for i in ("A", "B", "C")]
        edges = [_edge("E1", "A", "B"), _edge("E2", "B", "C")]
        clock = iter([0.0, 10.0, 20.0, 30.0, 40.0])
        with pytest.raises(NeighborTimeBudgetExceeded):
            traverse_neighbors(
                "A",
                store=GraphStore(nodes, edges),
                policy=AssuranceExposurePolicy("TLP:RED", True),
                budgets=NeighborBudgets(
                    max_hops=2, max_nodes=150, max_edges=300, time_budget_seconds=1.0,
                ),
                now=lambda: next(clock),
            )
