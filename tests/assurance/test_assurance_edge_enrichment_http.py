"""REST integration matrix for enriched assurance edges over a REAL seeded
SQLCipher store with a TLP mix (F2.1): name-resolved endpoints for visible
edges, total omission for hidden endpoints (no existence/type/direction
leakage anywhere in the payload), unknown vs above-ceiling indistinguishable,
and no-store semantics retained."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from tests.support.api_app import build_api_app

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_ASSURANCE_CTX_PATH = "src.infrastructure.rest.routers._assurance_read.get_assurance_context"


class _RealContext:
    def __init__(self, store: Any, ceiling: str) -> None:
        self.store = store
        self.max_classification = ceiling

    def is_available(self) -> bool:
        return self.store.is_unlocked()

    def locked_response(self) -> dict[str, Any]:
        return {"error": "assurance_store_locked", "message": "locked"}

    def not_found_response(self, node_id: str) -> dict[str, Any]:
        return {"error": "not_found", "node_id": node_id}


@pytest.fixture()
def seeded(tmp_path: Path):
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "enrichment.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    ids = {
        "hazard": store.create_node("hazard", "White Hazard", tlp="TLP:WHITE"),
        "loss": store.create_node("loss", "White Loss", tlp="TLP:WHITE"),
        "red_loss": store.create_node("loss", "RED LOSS NAME", tlp="TLP:RED"),
    }
    edges = {
        "visible": store.add_edge(ids["hazard"], ids["loss"], "leads-to"),
        "hidden": store.add_edge(ids["hazard"], ids["red_loss"], "leads-to"),
    }
    yield store, ids, edges
    store.lock()


def _client(store: Any, ceiling: str) -> TestClient:
    from src.infrastructure.rest.routers.assurance import router

    # `build_api_app`, not a bare `FastAPI()`: without the error contracts a raised `ApiError` never
    # becomes an envelope, so the test compares two empty bodies and calls them indistinguishable.
    client = TestClient(build_api_app(router), raise_server_exceptions=False)
    client._ctx_patch = patch(_ASSURANCE_CTX_PATH, return_value=_RealContext(store, ceiling))  # type: ignore[attr-defined]
    client._ctx_patch.start()  # type: ignore[attr-defined]
    return client


class TestNodeReadEnrichment:
    def test_visible_edges_are_name_resolved(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _edges = seeded
        client = _client(store, "TLP:AMBER")
        resp = client.get(f"/api/assurance/nodes/{ids['hazard']}")
        assert resp.status_code == 200
        body = resp.json()
        outgoing = body["outgoing_edges"]
        assert len(outgoing) == 1
        assert outgoing[0]["target_name"] == "White Loss"
        assert outgoing[0]["target_type"] == "loss"
        assert outgoing[0]["source_name"] == "White Hazard"
        assert body["visibility_limited"] is True

    def test_hidden_endpoint_leaks_nothing(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, edges = seeded
        client = _client(store, "TLP:AMBER")
        resp = client.get(f"/api/assurance/nodes/{ids['hazard']}")
        payload = resp.text
        assert ids["red_loss"] not in payload
        assert "RED LOSS NAME" not in payload
        assert edges["hidden"] not in payload
        # No withheld-edge count either — only the coarse policy-scope flag:
        assert "withheld" not in payload

    def test_raised_ceiling_reveals_the_edge_enriched(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _edges = seeded
        client = _client(store, "TLP:RED")
        body = client.get(f"/api/assurance/nodes/{ids['hazard']}").json()
        names = {e["target_name"] for e in body["outgoing_edges"]}
        assert names == {"White Loss", "RED LOSS NAME"}
        assert body["visibility_limited"] is False

    def test_unknown_and_above_ceiling_nodes_are_indistinguishable(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _edges = seeded
        client = _client(store, "TLP:AMBER")
        above = client.get(f"/api/assurance/nodes/{ids['red_loss']}")
        unknown = client.get("/api/assurance/nodes/LSS@does-not-exist")
        assert above.status_code == unknown.status_code
        # Compared without `request_id`, which the envelope makes unique per request on purpose. The
        # property is that nothing *about the resource* distinguishes the two: an above-ceiling node
        # and an absent one must read identically, or the 404 discloses that the node exists.
        above_detail = {k: v for k, v in above.json()["detail"].items() if k != "request_id"}
        unknown_detail = {k: v for k, v in unknown.json()["detail"].items() if k != "request_id"}
        assert above_detail == unknown_detail

    def test_no_store_semantics_retained(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _edges = seeded
        client = _client(store, "TLP:AMBER")
        resp = client.get(f"/api/assurance/nodes/{ids['hazard']}")
        assert resp.headers.get("Cache-Control") == "no-store"


class TestEdgeListEnrichment:
    def test_list_is_filtered_and_enriched(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _edges = seeded
        client = _client(store, "TLP:AMBER")
        body = client.get("/api/assurance/edges").json()
        assert body["count"] == 1
        edge = body["edges"][0]
        assert edge["source_name"] == "White Hazard"
        assert edge["target_name"] == "White Loss"
        assert ids["red_loss"] not in client.get("/api/assurance/edges").text
