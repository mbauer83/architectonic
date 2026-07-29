"""REST integration matrix for GET /api/assurance/neighbors over a REAL seeded
SQLCipher store: locked store, unknown vs above-ceiling roots, hidden nodes as
non-crossable (F2.2), hop clamping, size-budget truncation with frontier ids,
time-budget abort as a typed retryable 503, and no-store semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

pytest.importorskip("sqlcipher3", reason="sqlcipher3 not installed")

_CTX_PATH = "src.infrastructure.gui.routers._assurance_neighbors_routes.get_assurance_context"


class _RealContext:
    def __init__(self, store: Any, ceiling: str) -> None:
        self.store = store
        self.max_classification = ceiling

    def is_available(self) -> bool:
        return self.store.is_unlocked()


@pytest.fixture()
def seeded(tmp_path: Path):
    from src.infrastructure.assurance._sqlcipher_store import SQLCipherAssuranceStore
    from src.infrastructure.assurance.lifecycle import init_store

    db_path = tmp_path / "neighbors.db"
    init_store(db_path)
    store = SQLCipherAssuranceStore(db_path)
    store.unlock()
    ids = {
        "uca": store.create_node("unsafe-control-action", "White UCA", tlp="TLP:WHITE"),
        "hazard": store.create_node("hazard", "White Hazard", tlp="TLP:WHITE"),
        "loss": store.create_node("loss", "White Loss", tlp="TLP:WHITE"),
        "red_hazard": store.create_node("hazard", "RED HAZARD NAME", tlp="TLP:RED"),
        "red_loss": store.create_node("loss", "RED LOSS NAME", tlp="TLP:RED"),
    }
    edges = {
        "uca_hazard": store.add_edge(ids["uca"], ids["hazard"], "leads-to"),
        "hazard_loss": store.add_edge(ids["hazard"], ids["loss"], "leads-to"),
        # Pass-through chain: white uca → RED hazard → RED loss
        "uca_red": store.add_edge(ids["uca"], ids["red_hazard"], "leads-to"),
        "red_red": store.add_edge(ids["red_hazard"], ids["red_loss"], "leads-to"),
    }
    yield store, ids, edges
    store.lock()


def _client(store: Any, ceiling: str) -> TestClient:
    from src.infrastructure.gui.routers.assurance import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    client._ctx_patch = patch(_CTX_PATH, return_value=_RealContext(store, ceiling))  # type: ignore[attr-defined]
    client._ctx_patch.start()  # type: ignore[attr-defined]
    return client


class TestGating:
    def test_locked_store_returns_423(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _ = seeded
        client = _client(store, "TLP:AMBER")
        store.lock()
        try:
            resp = client.get(f"/api/assurance/neighbors?node_id={ids['uca']}")
            assert resp.status_code == 423
            assert resp.headers.get("Cache-Control") == "no-store"
        finally:
            store.unlock()

    def test_unknown_and_above_ceiling_roots_are_indistinguishable(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _ = seeded
        client = _client(store, "TLP:AMBER")
        above = client.get(f"/api/assurance/neighbors?node_id={ids['red_hazard']}")
        unknown = client.get("/api/assurance/neighbors?node_id=HAZ@does-not-exist")
        assert above.status_code == unknown.status_code == 404
        assert above.json() == unknown.json()

    def test_no_store_semantics(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _ = seeded
        client = _client(store, "TLP:AMBER")
        resp = client.get(f"/api/assurance/neighbors?node_id={ids['uca']}")
        assert resp.headers.get("Cache-Control") == "no-store"


class TestTraversal:
    def test_one_hop_default_with_annotations(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _ = seeded
        client = _client(store, "TLP:RED")
        body = client.get(f"/api/assurance/neighbors?node_id={ids['uca']}").json()
        assert body["root_id"] == ids["uca"]
        assert body["max_hops"] == 1
        hops = {n["node_id"]: n["hop"] for n in body["nodes"]}
        assert hops == {ids["uca"]: 0, ids["hazard"]: 1, ids["red_hazard"]: 1}
        roots = [n["node_id"] for n in body["nodes"] if n["is_root"]]
        assert roots == [ids["uca"]]
        assert all(e["direction"] == "outgoing" for e in body["edges"])
        assert {e["target_name"] for e in body["edges"]} == {"White Hazard", "RED HAZARD NAME"}

    def test_hidden_node_is_not_crossed_and_leaks_nothing(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, edges = seeded
        client = _client(store, "TLP:AMBER")
        resp = client.get(f"/api/assurance/neighbors?node_id={ids['uca']}&max_hops=4")
        body = resp.json()
        # The white chain is fully reachable; the red chain is absent entirely.
        assert {n["node_id"] for n in body["nodes"]} == {ids["uca"], ids["hazard"], ids["loss"]}
        payload = resp.text
        assert ids["red_hazard"] not in payload
        assert ids["red_loss"] not in payload
        assert "RED HAZARD NAME" not in payload
        assert "RED LOSS NAME" not in payload
        assert edges["uca_red"] not in payload
        assert edges["red_red"] not in payload
        assert "withheld" not in payload
        assert body["truncated"] is False  # omission is silent, never truncation
        assert body["visibility_limited"] is True

    def test_max_hops_is_clamped(self, seeded) -> None:  # type: ignore[no-untyped-def]
        store, ids, _ = seeded
        client = _client(store, "TLP:RED")
        zero = client.get(f"/api/assurance/neighbors?node_id={ids['uca']}&max_hops=0").json()
        huge = client.get(f"/api/assurance/neighbors?node_id={ids['uca']}&max_hops=99").json()
        assert zero["max_hops"] == 1
        assert huge["max_hops"] == 4


class TestBudgets:
    def test_node_budget_truncates_with_frontier(self, seeded, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        import src.infrastructure.gui.routers._assurance_neighbors_routes as routes

        store, ids, _ = seeded
        monkeypatch.setattr(routes, "assurance_neighbors_max_nodes", lambda: 2)
        client = _client(store, "TLP:RED")
        body = client.get(f"/api/assurance/neighbors?node_id={ids['uca']}").json()
        assert body["truncated"] is True
        assert body["frontier_node_ids"] == [ids["uca"]]
        assert len(body["nodes"]) == 2
        assert len(body["edges"]) == 1  # the cut node's edge is omitted with it

    def test_time_budget_exceeded_is_a_typed_retryable_503(self, seeded, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        import src.application.assurance_neighbors as traversal_module
        import src.infrastructure.gui.routers._assurance_neighbors_routes as routes

        store, ids, _ = seeded
        monkeypatch.setattr(
            routes, "traverse_neighbors",
            lambda *a, **k: (_ for _ in ()).throw(traversal_module.NeighborTimeBudgetExceeded()),
        )
        client = _client(store, "TLP:RED")
        resp = client.get(f"/api/assurance/neighbors?node_id={ids['uca']}")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "traversal_time_budget_exceeded"
        assert body["retryable"] is True
        assert "nodes" not in body  # no partial graph
        assert resp.headers.get("Cache-Control") == "no-store"
        assert resp.headers.get("Retry-After") == "1"
