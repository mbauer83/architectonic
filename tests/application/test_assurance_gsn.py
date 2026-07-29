from __future__ import annotations

from typing import Any

from src.application.assurance_gsn import build_gsn_draft, record_publication


class _Store:
    def __init__(self) -> None:
        self.refs: list[tuple[str, str, str]] = []
        self.analysis = {
            "analysis_id": "AN@1",
            "name": "Brake safety",
            "tlp": "TLP:GREEN",
        }
        self.nodes = [
            {"node_id": "L@1", "node_type": "loss", "name": "Loss", "tlp": "TLP:WHITE"},
            {"node_id": "H@1", "node_type": "hazard", "name": "Hazard", "tlp": "TLP:GREEN"},
            {"node_id": "U@1", "node_type": "unsafe-control-action", "name": "UCA"},
            {"node_id": "C@1", "node_type": "assurance-constraint", "name": "Constraint"},
            {"node_id": "E@1", "node_type": "evidence", "name": "Report"},
        ]
        self.edges = [
            {"source_id": "H@1", "target_id": "L@1", "conn_type": "leads-to"},
            {"source_id": "U@1", "target_id": "H@1", "conn_type": "leads-to"},
            {"source_id": "U@1", "target_id": "C@1", "conn_type": "derives"},
            {"source_id": "C@1", "target_id": "E@1", "conn_type": "evidenced-by"},
        ]

    def get_analysis(self, analysis_id: str) -> dict[str, object] | None:
        return self.analysis if analysis_id == "AN@1" else None

    def list_nodes(self, **_kwargs: Any) -> list[dict[str, object]]:
        return self.nodes

    def list_edges(self, **_kwargs: Any) -> list[dict[str, object]]:
        return self.edges

    def get_node(self, node_id: str) -> dict[str, object] | None:
        return next((node for node in self.nodes if node["node_id"] == node_id), None)

    def register_arch_ref(self, assurance_node_id: str, arch_artifact_id: str, ref_type: str) -> None:
        self.refs.append((assurance_node_id, arch_artifact_id, ref_type))


class _Archive:
    def __init__(self) -> None:
        self.entries: list[tuple[str, dict[str, object]]] = []

    def append(self, operation: str, **kwargs: object) -> dict[str, object]:
        self.entries.append((operation, dict(kwargs)))
        return {"operation": operation}


def test_build_gsn_draft_creates_argument_and_bindable_sources() -> None:
    result = build_gsn_draft(_Store(), analysis_id="AN@1")
    assert result is not None
    assert result["effective_tlp"] == "TLP:GREEN"
    assert result["publishable"] is True
    entities = result["diagram_entities"]
    assert isinstance(entities, dict)
    node_types = {node["gsn_type"] for node in entities["nodes"]}  # type: ignore[index]
    assert {"goal", "strategy", "solution", "context"} <= node_types
    assert any(node["source_assurance_ids"] for node in entities["nodes"])  # type: ignore[index]


def test_record_publication_registers_source_bridge_and_audits() -> None:
    store = _Store()
    archive = _Archive()
    result = record_publication(
        store,
        archive,
        analysis_id="AN@1",
        diagram_id="GSN@1.case",
        source_bindings=[{"assurance_node_id": "H@1", "gsn_node_id": "G-H@1"}],
    )
    assert result["status"] == "published"
    assert store.refs == [("H@1", "GSN@1.case#nodes/G-H@1", "gsn-source")]
    assert archive.entries[0][0] == "PUBLISH_GSN"
