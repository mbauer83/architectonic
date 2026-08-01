"""Connection counts for assurance nodes, and the confidentiality boundary they sit inside.

The counts themselves are arithmetic. The property worth testing is the one that is easy to get
wrong and invisible when wrong: a degree taken over the unfiltered edge set leaks the existence
of above-ceiling neighbours, because the reader sees a number larger than the edges they can
account for. That is a disclosure, not a display bug, so it is asserted here rather than left to
the endpoint.
"""

from __future__ import annotations

from typing import Any

from src.application.assurance.exposure import AssuranceExposurePolicy
from src.application.assurance.node_degrees import degrees_by_node_id, with_degrees


def _node(node_id: str, tlp: str = "TLP:WHITE") -> dict[str, Any]:
    return {"node_id": node_id, "name": node_id, "node_type": "hazard", "tlp": tlp}


def _edge(source: str, target: str, conn_type: str = "leads-to") -> dict[str, Any]:
    return {"edge_id": f"{source}->{target}", "source_id": source, "target_id": target, "conn_type": conn_type}


class TestDegreeCounting:
    def test_counts_each_side_of_an_edge_separately(self) -> None:
        degrees = degrees_by_node_id([_edge("a", "b")])

        assert degrees["a"].conn_out == 1
        assert degrees["a"].conn_in == 0
        assert degrees["b"].conn_in == 1
        assert degrees["b"].conn_out == 0

    def test_total_is_the_sum_of_both_directions(self) -> None:
        degrees = degrees_by_node_id([_edge("a", "b"), _edge("c", "a")])

        assert degrees["a"].total == 2

    def test_a_self_edge_counts_once_on_each_side(self) -> None:
        """Which is what both of its endpoints are — the node is genuinely both."""
        degrees = degrees_by_node_id([_edge("a", "a")])

        assert (degrees["a"].conn_in, degrees["a"].conn_out) == (1, 1)

    def test_parallel_edges_of_different_types_each_count(self) -> None:
        degrees = degrees_by_node_id([_edge("a", "b", "leads-to"), _edge("a", "b", "mitigates")])

        assert degrees["a"].conn_out == 2

    def test_no_edges_yields_no_entries(self) -> None:
        assert degrees_by_node_id([]) == {}


class TestDecoratingNodes:
    def test_every_node_reports_its_counts(self) -> None:
        decorated = with_degrees([_node("a"), _node("b")], [_edge("a", "b")])

        by_id = {n["node_id"]: n for n in decorated}
        assert (by_id["a"]["conn_in"], by_id["a"]["conn_out"]) == (0, 1)
        assert (by_id["b"]["conn_in"], by_id["b"]["conn_out"]) == (1, 0)

    def test_an_isolated_node_reports_zero_rather_than_omitting_the_field(self) -> None:
        """So a reader can tell "unconnected" from "not counted"."""
        decorated = with_degrees([_node("lonely")], [])

        assert decorated[0]["conn_in"] == 0
        assert decorated[0]["conn_out"] == 0

    def test_the_node_s_own_fields_survive(self) -> None:
        decorated = with_degrees([_node("a")], [])

        assert decorated[0]["name"] == "a"
        assert decorated[0]["node_type"] == "hazard"


class TestCountsRespectTheExposureCeiling:
    """The disclosure test.

    A count is only correct relative to the reader's clearance. Taken over the raw edge set it
    reports relations to nodes the reader may not know exist — and the discrepancy between the
    number and the visible edges is itself the leak.
    """

    def test_an_edge_to_an_above_ceiling_node_is_not_counted(self) -> None:
        nodes = [_node("public"), _node("secret", tlp="TLP:RED")]
        edges = [_edge("public", "secret")]
        policy = AssuranceExposurePolicy(ceiling="TLP:GREEN", is_unlocked=True)

        visible, _withheld = policy.filter_nodes(nodes)
        visible_ids = frozenset(str(n["node_id"]) for n in visible)
        decorated = with_degrees(visible, policy.filter_edges(edges, visible_ids))

        assert [n["node_id"] for n in decorated] == ["public"]
        assert decorated[0]["conn_out"] == 0, "the count discloses a classified neighbour"

    def test_edges_between_visible_nodes_are_still_counted(self) -> None:
        """The filter must not be so blunt that it reports nothing to a restricted reader."""
        nodes = [_node("a"), _node("b"), _node("secret", tlp="TLP:RED")]
        edges = [_edge("a", "b"), _edge("a", "secret")]
        policy = AssuranceExposurePolicy(ceiling="TLP:GREEN", is_unlocked=True)

        visible, _withheld = policy.filter_nodes(nodes)
        visible_ids = frozenset(str(n["node_id"]) for n in visible)
        decorated = with_degrees(visible, policy.filter_edges(edges, visible_ids))

        by_id = {n["node_id"]: n for n in decorated}
        assert by_id["a"]["conn_out"] == 1
        assert by_id["b"]["conn_in"] == 1

    def test_a_cleared_reader_sees_the_full_degree(self) -> None:
        nodes = [_node("public"), _node("secret", tlp="TLP:RED")]
        edges = [_edge("public", "secret")]
        policy = AssuranceExposurePolicy(ceiling="TLP:RED", is_unlocked=True)

        visible, _withheld = policy.filter_nodes(nodes)
        visible_ids = frozenset(str(n["node_id"]) for n in visible)
        decorated = with_degrees(visible, policy.filter_edges(edges, visible_ids))

        by_id = {n["node_id"]: n for n in decorated}
        assert by_id["public"]["conn_out"] == 1
