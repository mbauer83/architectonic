"""Endpoint enrichment over policy-filtered assurance edges: the I-B1 unit matrix
(TLP mix → omission with no placeholders or counts; dangling endpoints omitted)
and the enrichment contract itself."""

from __future__ import annotations

import json
from typing import Any

from src.application.assurance_edge_enrichment import enrich_edges, visible_nodes_by_id
from src.application.assurance_exposure import AssuranceExposurePolicy


def _node(node_id: str, name: str, node_type: str = "hazard", tlp: str = "TLP:WHITE") -> dict[str, Any]:
    return {"node_id": node_id, "name": name, "node_type": node_type, "tlp": tlp}


def _edge(source: str, target: str, conn_type: str = "leads-to", edge_id: str = "E1") -> dict[str, Any]:
    return {"edge_id": edge_id, "source_id": source, "target_id": target, "conn_type": conn_type}


class TestEnrichment:
    def test_edges_gain_endpoint_names_and_types(self) -> None:
        nodes = [_node("HAZ@1", "Hazard One"), _node("LSS@1", "Loss One", node_type="loss")]
        enriched = enrich_edges([_edge("HAZ@1", "LSS@1")], visible_nodes_by_id(nodes))
        assert enriched == [{
            "edge_id": "E1",
            "source_id": "HAZ@1",
            "target_id": "LSS@1",
            "conn_type": "leads-to",
            "source_name": "Hazard One",
            "source_type": "hazard",
            "target_name": "Loss One",
            "target_type": "loss",
        }]

    def test_lookup_miss_omits_the_edge_never_a_placeholder(self) -> None:
        nodes = [_node("HAZ@1", "Hazard One")]
        enriched = enrich_edges(
            [_edge("HAZ@1", "LSS@gone"), _edge("LSS@gone", "HAZ@1", edge_id="E2")],
            visible_nodes_by_id(nodes),
        )
        assert enriched == []


class TestOmissionMatrix:
    """Policy filtering + enrichment composed over a TLP mix (F2.1/F2.8)."""

    def _pipeline(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], ceiling: str):
        policy = AssuranceExposurePolicy(ceiling, True)
        visible, _withheld = policy.filter_nodes(nodes)
        nodes_by_id = visible_nodes_by_id(visible)
        return enrich_edges(policy.filter_edges(edges, frozenset(nodes_by_id)), nodes_by_id)

    def test_edge_with_hidden_endpoint_is_absent_entirely(self) -> None:
        nodes = [
            _node("HAZ@w", "White Hazard"),
            _node("LSS@r", "RED LOSS NAME", node_type="loss", tlp="TLP:RED"),
            _node("LSS@w", "White Loss", node_type="loss"),
        ]
        edges = [
            _edge("HAZ@w", "LSS@r", edge_id="E-hidden"),
            _edge("HAZ@w", "LSS@w", edge_id="E-visible"),
        ]
        result = self._pipeline(nodes, edges, "TLP:AMBER")
        assert [e["edge_id"] for e in result] == ["E-visible"]
        # No placeholder, count, existence, type, or direction leakage anywhere:
        payload = json.dumps(result)
        assert "LSS@r" not in payload
        assert "RED LOSS NAME" not in payload
        assert "E-hidden" not in payload

    def test_hidden_source_and_hidden_target_are_indistinguishable(self) -> None:
        nodes = [
            _node("HAZ@w", "White Hazard"),
            _node("UCA@r", "Red UCA", node_type="unsafe-control-action", tlp="TLP:RED"),
        ]
        outgoing = self._pipeline(nodes, [_edge("HAZ@w", "UCA@r")], "TLP:AMBER")
        incoming = self._pipeline(nodes, [_edge("UCA@r", "HAZ@w")], "TLP:AMBER")
        assert outgoing == incoming == []

    def test_dangling_endpoint_edge_is_omitted_like_a_hidden_one(self) -> None:
        nodes = [_node("HAZ@w", "White Hazard")]
        result = self._pipeline(nodes, [_edge("HAZ@w", "LSS@deleted")], "TLP:RED")
        assert result == []

    def test_full_visibility_enriches_everything(self) -> None:
        nodes = [
            _node("HAZ@w", "White Hazard"),
            _node("LSS@r", "Red Loss", node_type="loss", tlp="TLP:RED"),
        ]
        result = self._pipeline(nodes, [_edge("HAZ@w", "LSS@r")], "TLP:RED")
        assert len(result) == 1
        assert result[0]["target_name"] == "Red Loss"
