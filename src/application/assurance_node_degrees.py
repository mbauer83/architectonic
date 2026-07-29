"""Connection counts for assurance nodes, computed over the visible edge set.

The architecture browse surface has shown a node's degree for as long as it has had a table,
because "how connected is this?" is the first question asked of a list of model elements. The
assurance list answered it only by opening a node. This closes that gap.

Two things differ from the architecture side, and both are properties of the assurance model
rather than choices made here:

* **No symmetric count.** Architecture connection types carry a `symmetric` flag from the
  ontology, so a relation can be genuinely undirected. Assurance edges have no ontology behind
  them — `conn_type` is free text on a strictly directed `(source_id, target_id)` — so there is
  nothing to classify as symmetric. Reporting a permanently-zero `sym` would assert that a node
  has no undirected relations, when the truth is that the concept does not apply.
* **Computed per request, not precomputed.** Architecture reads `entity_context_stats`, a table
  maintained by the indexer. The assurance store has no such table, and it must not: a count is
  only correct relative to the reader's clearance, so a stored figure would be right for exactly
  one ceiling. See below.

**Confidentiality.** Degrees are derived strictly from edges that survive
`AssuranceExposurePolicy.filter_edges` over the visible node set — the same contract
`enrich_edges` states. Counting before that filter would publish the existence of above-ceiling
neighbours: a reader would see "3 outgoing" against two visible edges and learn that a third,
classified, relation exists. The count is part of the exposure surface, so it is computed inside
it.
"""

from __future__ import annotations

from typing import Any, Final, NamedTuple


class NodeDegrees(NamedTuple):
    """Incoming and outgoing edge counts for one node."""

    conn_in: int
    conn_out: int

    @property
    def total(self) -> int:
        return self.conn_in + self.conn_out


_ZERO: Final = NodeDegrees(conn_in=0, conn_out=0)


def degrees_by_node_id(visible_edges: list[dict[str, Any]]) -> dict[str, NodeDegrees]:
    """Count incoming and outgoing edges per node id.

    `visible_edges` MUST already be policy-filtered over the visible node set; see the module
    docstring. A self-edge counts once on each side, which is what both endpoints of it are.
    """
    incoming: dict[str, int] = {}
    outgoing: dict[str, int] = {}
    for edge in visible_edges:
        source = str(edge.get("source_id", ""))
        target = str(edge.get("target_id", ""))
        if source:
            outgoing[source] = outgoing.get(source, 0) + 1
        if target:
            incoming[target] = incoming.get(target, 0) + 1

    return {
        node_id: NodeDegrees(conn_in=incoming.get(node_id, 0), conn_out=outgoing.get(node_id, 0))
        for node_id in incoming.keys() | outgoing.keys()
    }


def with_degrees(
    visible_nodes: list[dict[str, Any]],
    visible_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return `visible_nodes` each decorated with `conn_in` / `conn_out`.

    Every node gets the keys, including isolated ones — a node with no edges reports zero
    rather than omitting the field, so the reader can tell "unconnected" from "not counted".
    """
    degrees = degrees_by_node_id(visible_edges)
    return [
        {
            **node,
            "conn_in": degrees.get(str(node.get("node_id", "")), _ZERO).conn_in,
            "conn_out": degrees.get(str(node.get("node_id", "")), _ZERO).conn_out,
        }
        for node in visible_nodes
    ]
