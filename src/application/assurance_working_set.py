"""The graph one analysis reasons over: what it authored, plus what it borrowed.

Every surface scoped to a single analysis needs the same answer, and it is not
``list_nodes(analysis_id=…)``. That returns only the nodes the analysis *authored*, and an analysis
that draws on another's work has more than that in front of it: an FMEA enumerates failure modes
against the control-structure nodes an STPA identified, and those nodes are the STPA's.

So the working set is **authored ∪ participating**. Getting this wrong in either direction breaks
something specific:

* Authored only — the FMEA's matrix has no components to put rows against, its edge pickers cannot
  reach the hazard a failure mode leads to, and the analyst's only remaining option is to copy the
  STPA's nodes, which then drift.
* Everything in the store — an analysis' own diagram shows another analysis' findings, and the
  scoping this module exists to provide is gone.

**Confidentiality.** The set is filtered through `AssuranceExposurePolicy` before it is returned,
nodes and edges alike, so nothing downstream has to remember to do it. Edges survive only when both
endpoints are in the visible set: an edge with a hidden endpoint discloses that node's existence,
which is the same rule `enrich_edges` and `assurance_node_degrees` follow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from src.application.assurance_exposure import AssuranceExposurePolicy
    from src.application.assurance_ports import ConfidentialAssuranceStore


class AnalysisWorkingSet(NamedTuple):
    """The visible graph of one analysis, and which of its nodes it authored.

    `authored_node_ids` is carried alongside rather than derived by the caller, because the
    distinction is the one thing a reader of a combined analysis must not lose: a borrowed node has
    to look borrowed.
    """

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    authored_node_ids: frozenset[str]

    @property
    def node_ids(self) -> frozenset[str]:
        return frozenset(str(node.get("node_id", "")) for node in self.nodes)


def analysis_working_set(
    store: ConfidentialAssuranceStore,
    policy: AssuranceExposurePolicy,
    analysis_id: str,
) -> AnalysisWorkingSet:
    """Return the exposure-filtered nodes and edges ``analysis_id`` reasons over."""
    authored, _withheld = policy.filter_nodes(store.list_nodes(analysis_id=analysis_id))
    authored_ids = frozenset(str(node.get("node_id", "")) for node in authored)

    borrowed_ids = [
        node_id for node_id in store.list_analysis_members(analysis_id)
        if node_id not in authored_ids
    ]
    borrowed_records = [store.get_node(node_id) for node_id in borrowed_ids]
    borrowed, _withheld_borrowed = policy.filter_nodes(
        [record for record in borrowed_records if record is not None]
    )

    nodes = [*authored, *borrowed]
    node_ids = frozenset(str(node.get("node_id", "")) for node in nodes)
    edges = policy.filter_edges(store.list_edges(), node_ids)
    return AnalysisWorkingSet(nodes=nodes, edges=edges, authored_node_ids=authored_ids)
