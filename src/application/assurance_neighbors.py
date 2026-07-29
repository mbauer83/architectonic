"""Bounded, cycle-safe neighbor traversal over the confidential assurance graph.

Contract:
- Size budgets (``max_nodes``, ``max_edges``) define partial results:
  ``truncated=True`` plus the visible frontier node ids whose expansion was cut
  short — the client expands a frontier node with a new request. Ordering is
  deterministic for a given store state, so re-running yields the same graph.
  There are no continuation tokens.
- The time budget aborts the WHOLE request via ``NeighborTimeBudgetExceeded``
  (typed, retryable) — never a partial graph, because wall-clock truncation is
  not deterministic and must not mix with the deterministic size budgets.
- Exposure omission per hop: the traversal only ever stands on visible nodes,
  so an above-ceiling node is never crossed, not even as a pass-through hop,
  and no edge touching it is returned.
- Cycles terminate via the visited set. A self-loop appears once with
  ``direction="self"``. Multiedges are distinct edges and each counts toward
  the edge budget.
- The root is included with ``hop=0`` and ``is_root=True``. Every node carries
  its hop distance; every edge carries the hop at which it was discovered and
  its direction relative to the node it was discovered from. Edges are only
  discovered from expanded nodes — two nodes both first reached at the final
  hop may have an edge between them that is not returned; expanding either
  node returns it.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Protocol

from src.application.assurance_edge_enrichment import enrich_edges, visible_nodes_by_id
from src.application.assurance_exposure import AssuranceExposurePolicy


class NeighborGraphReads(Protocol):
    """The two store reads the traversal needs (satisfied by ConfidentialAssuranceStore)."""

    def list_nodes(self) -> list[dict[str, object]]: ...

    def list_edges(
        self,
        *,
        source_id: str | None = None,
        target_id: str | None = None,
    ) -> list[dict[str, object]]: ...


class NeighborTimeBudgetExceeded(Exception):
    """The traversal ran past its wall-clock budget; retry (results would not be
    deterministic, so nothing partial is returned)."""


@dataclass(frozen=True)
class NeighborBudgets:
    """Effective budgets for one traversal; callers clamp before constructing."""

    max_hops: int
    max_nodes: int
    max_edges: int
    time_budget_seconds: float


@dataclass(frozen=True)
class NeighborhoodGraph:
    """One policy-filtered neighborhood; transient, never persisted."""

    root_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    truncated: bool
    frontier_node_ids: list[str]


def _edge_sort_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("conn_type", "")),
        str(edge.get("source_id", "")),
        str(edge.get("target_id", "")),
        str(edge.get("edge_id", "")),
    )


def _edge_direction(edge: dict[str, Any], from_node_id: str) -> str:
    source = str(edge.get("source_id", ""))
    target = str(edge.get("target_id", ""))
    if source == target:
        return "self"
    return "outgoing" if source == from_node_id else "incoming"


def _incident_visible_edges(
    store: NeighborGraphReads,
    policy: AssuranceExposurePolicy,
    node_id: str,
    visible_ids: frozenset[str],
) -> list[dict[str, Any]]:
    incident = store.list_edges(source_id=node_id) + store.list_edges(target_id=node_id)
    deduped = {str(e.get("edge_id", "")): e for e in incident}  # self-loops appear in both lists
    return sorted(policy.filter_edges(list(deduped.values()), visible_ids), key=_edge_sort_key)


def traverse_neighbors(
    root_id: str,
    *,
    store: NeighborGraphReads,
    policy: AssuranceExposurePolicy,
    budgets: NeighborBudgets,
    now: Callable[[], float] = monotonic,
) -> NeighborhoodGraph | None:
    """Breadth-first neighborhood of ``root_id``, or None when the root is
    absent or above ceiling (callers keep the two indistinguishable)."""
    visible_nodes, _ = policy.filter_nodes(store.list_nodes())
    nodes_by_id = visible_nodes_by_id(visible_nodes)
    if root_id not in nodes_by_id:
        return None
    visible_ids = frozenset(nodes_by_id)

    deadline = now() + budgets.time_budget_seconds
    hops: dict[str, int] = {root_id: 0}
    edges_by_id: dict[str, dict[str, Any]] = {}
    truncated = False
    frontier_cut: set[str] = set()
    frontier = [root_id]

    for hop in range(1, budgets.max_hops + 1):
        next_frontier: list[str] = []
        for node_id in sorted(frontier):
            if now() > deadline:
                raise NeighborTimeBudgetExceeded
            for edge in _incident_visible_edges(store, policy, node_id, visible_ids):
                edge_id = str(edge.get("edge_id", ""))
                if edge_id in edges_by_id:
                    continue
                if len(edges_by_id) >= budgets.max_edges:
                    truncated = True
                    frontier_cut.add(node_id)
                    continue
                source = str(edge.get("source_id", ""))
                target = str(edge.get("target_id", ""))
                other = target if source == node_id else source
                if other not in hops:
                    if len(hops) >= budgets.max_nodes:
                        truncated = True
                        frontier_cut.add(node_id)
                        continue  # edge omitted too: it would reference an absent node
                    hops[other] = hop
                    next_frontier.append(other)
                edges_by_id[edge_id] = {
                    **edge,
                    "hop": hop,
                    "direction": _edge_direction(edge, node_id),
                }
        frontier = next_frontier

    nodes = [
        {**nodes_by_id[node_id], "hop": hop, "is_root": node_id == root_id}
        for node_id, hop in sorted(hops.items(), key=lambda item: (item[1], item[0]))
    ]
    return NeighborhoodGraph(
        root_id=root_id,
        nodes=nodes,
        edges=enrich_edges(list(edges_by_id.values()), nodes_by_id),
        truncated=truncated,
        frontier_node_ids=sorted(frontier_cut),
    )
