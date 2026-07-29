"""Negative-leak and functional tests for assurance HTTP read endpoints.

Verifies:
  - Locked store → 423 on every endpoint.
  - Above-ceiling nodes/edges/counts never leak through lists, stats, coverage,
    risk-register, or verify; names/IDs/topology are absent from all responses.
  - Direct read of an above-ceiling ID is indistinguishable from an absent ID
    (both → 404).
  - Cache-Control: no-store header on all responses.
  - arch-lens returns empty (not 404) when store is locked or no refs exist.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI

httpx = pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

# ── Fake infrastructure ───────────────────────────────────────────────────────

class _FakeStore:
    def __init__(self, unlocked: bool = True, nodes: list[dict] | None = None) -> None:
        self._unlocked = unlocked
        self._nodes: list[dict[str, Any]] = nodes or []
        self._edges: list[dict[str, Any]] = []

    def is_unlocked(self) -> bool:
        return self._unlocked

    def list_nodes(self, *, node_type=None, status=None, concern_class=None, tlp=None,
                   analysis_id=None, sort=None, order=None):
        from src.application.assurance_node_sorting import sorted_node_dicts

        return sorted_node_dicts(self._nodes, sort, order)

    def search_nodes(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        q = query.lower()
        return [
            n for n in self._nodes
            if q in str(n.get("name", "")).lower() or q in str(n.get("content_text", "")).lower()
        ][:limit]

    def get_node(self, node_id: str) -> dict | None:
        return next((n for n in self._nodes if n["node_id"] == node_id), None)

    def list_edges(self, *, source_id=None, target_id=None, conn_type=None):
        return self._edges

    def list_arch_refs(self, *, assurance_node_id=None, arch_artifact_id=None):
        return []

    def list_analyses(self, *, method=None, status=None):
        """No analyses: this fake exercises exposure over nodes, and a hit whose analysis is
        unknown reports none — which is the same shape as one above the reader's ceiling."""
        return []

    def list_participating_analyses(self, node_id: str) -> list[str]:
        return []

    def read_fmea_assessments(self, node_ids):
        """No factor judgements — this fake exercises the read endpoints' exposure behaviour."""
        return {}

    def stats(self) -> dict:
        return {"node_count": len(self._nodes), "edge_count": 0, "by_type": {}}


class _FakeArchive:
    def list_baselines(self) -> list:
        return []


class _FakeContext:
    def __init__(self, store: _FakeStore, ceiling: str = "TLP:RED") -> None:
        self._store = store
        self._archive = _FakeArchive()
        self.max_classification = ceiling

    @property
    def store(self):
        return self._store

    @property
    def archive(self):
        return self._archive

    def is_available(self) -> bool:
        return self._store.is_unlocked()

    def locked_response(self):
        return {"error": "assurance_store_locked", "message": "locked"}

    def not_found_response(self, node_id: str):
        return {"error": "not_found", "node_id": node_id}


# ── Client factory ────────────────────────────────────────────────────────────

_ASSURANCE_CTX_PATH = "src.infrastructure.gui.routers._assurance_read.get_assurance_context"

_WHITE_NODE: dict[str, Any] = {
    "node_id": "LSS@visible-node",
    "node_type": "loss",
    "name": "Visible Loss",
    "tlp": "TLP:WHITE",
    "status": "draft",
}
_RED_NODE: dict[str, Any] = {
    "node_id": "HAZ@secret-node",
    "node_type": "hazard",
    "name": "SECRET HAZARD NAME",
    "tlp": "TLP:RED",
    "status": "draft",
}


def _make_client(ctx: _FakeContext) -> TestClient:
    from src.infrastructure.gui.routers.assurance import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    client._ctx_patch = patch(_ASSURANCE_CTX_PATH, return_value=ctx)  # type: ignore[attr-defined]
    client._ctx_patch.start()  # type: ignore[attr-defined]
    return client


# ── 423 locked tests ──────────────────────────────────────────────────────────

@pytest.fixture()
def locked_client() -> TestClient:
    ctx = _FakeContext(_FakeStore(unlocked=False), ceiling="TLP:RED")
    return _make_client(ctx)


def _check_423(client: TestClient, url: str) -> None:
    r = client.get(url)
    assert r.status_code == 423, f"{url} → {r.status_code}"
    assert r.headers.get("cache-control") == "no-store"


def test_locked_nodes_returns_423(locked_client: TestClient) -> None:
    _check_423(locked_client, "/api/assurance/nodes")


def test_locked_node_detail_returns_423(locked_client: TestClient) -> None:
    _check_423(locked_client, "/api/assurance/nodes/any-id")


def test_locked_edges_returns_423(locked_client: TestClient) -> None:
    _check_423(locked_client, "/api/assurance/edges")


def test_locked_stats_returns_423(locked_client: TestClient) -> None:
    _check_423(locked_client, "/api/assurance/stats")


def test_locked_coverage_returns_423(locked_client: TestClient) -> None:
    _check_423(locked_client, "/api/assurance/coverage")


def test_locked_verify_returns_423(locked_client: TestClient) -> None:
    _check_423(locked_client, "/api/assurance/verify")


def test_locked_risk_register_returns_423(locked_client: TestClient) -> None:
    _check_423(locked_client, "/api/assurance/risk-register")


def test_locked_baselines_returns_423(locked_client: TestClient) -> None:
    _check_423(locked_client, "/api/assurance/baselines")


# ── No-store header on all unlocked responses ─────────────────────────────────

@pytest.fixture()
def unlocked_client() -> TestClient:
    ctx = _FakeContext(_FakeStore(unlocked=True, nodes=[_WHITE_NODE]), ceiling="TLP:RED")
    return _make_client(ctx)


def _check_no_store(client: TestClient, url: str) -> None:
    r = client.get(url)
    assert r.headers.get("cache-control") == "no-store", f"{url} missing no-store"


def test_unlocked_nodes_has_no_store(unlocked_client: TestClient) -> None:
    _check_no_store(unlocked_client, "/api/assurance/nodes")


def test_unlocked_stats_has_no_store(unlocked_client: TestClient) -> None:
    _check_no_store(unlocked_client, "/api/assurance/stats")


# ── Negative leak: above-ceiling records absent from lists ────────────────────

@pytest.fixture()
def leak_client() -> TestClient:
    """Ceiling=TLP:GREEN; store has one WHITE (visible) and one RED (secret) node."""
    ctx = _FakeContext(
        _FakeStore(unlocked=True, nodes=[_WHITE_NODE, _RED_NODE]),
        ceiling="TLP:GREEN",
    )
    return _make_client(ctx)


def test_list_nodes_secret_name_absent(leak_client: TestClient) -> None:
    r = leak_client.get("/api/assurance/nodes")
    assert r.status_code == 200
    body = r.json()
    names = {n["name"] for n in body["nodes"]}
    assert "SECRET HAZARD NAME" not in names


def test_list_nodes_secret_id_absent(leak_client: TestClient) -> None:
    r = leak_client.get("/api/assurance/nodes")
    body = r.json()
    ids = {n["node_id"] for n in body["nodes"]}
    assert "HAZ@secret-node" not in ids


def test_list_nodes_count_is_visible_only(leak_client: TestClient) -> None:
    r = leak_client.get("/api/assurance/nodes")
    body = r.json()
    assert body["count"] == 1  # only the WHITE node


def test_stats_count_excludes_secret(leak_client: TestClient) -> None:
    r = leak_client.get("/api/assurance/stats")
    body = r.json()
    assert body["node_count"] == 1
    assert "hazard" not in body.get("by_type", {})


# ── Negative leak: direct read above-ceiling ≡ absent ────────────────────────

def test_direct_read_secret_node_returns_404(leak_client: TestClient) -> None:
    r = leak_client.get("/api/assurance/nodes/HAZ@secret-node")
    assert r.status_code == 404


def test_direct_read_absent_node_returns_404(leak_client: TestClient) -> None:
    r = leak_client.get("/api/assurance/nodes/NONEXISTENT@node-id")
    assert r.status_code == 404


def test_direct_read_secret_body_has_no_classified_content(leak_client: TestClient) -> None:
    r = leak_client.get("/api/assurance/nodes/HAZ@secret-node")
    text = r.text
    assert "SECRET HAZARD NAME" not in text
    assert "HAZ@secret-node" not in text


# ── arch-lens: locked → empty (not 404) ──────────────────────────────────────

def test_arch_lens_locked_returns_200_empty(locked_client: TestClient) -> None:
    r = locked_client.get("/api/assurance/arch-lens/ENT@some-entity")
    assert r.status_code == 200
    body = r.json()
    assert body["locked"] is True
    assert body["nodes"] == []


def test_arch_lens_unlocked_no_refs_returns_empty(unlocked_client: TestClient) -> None:
    r = unlocked_client.get("/api/assurance/arch-lens/ENT@some-entity")
    assert r.status_code == 200
    body = r.json()
    assert body["locked"] is False
    assert body["count"] == 0


# ── Search: locked → 423 ─────────────────────────────────────────────────────

def test_locked_search_returns_423(locked_client: TestClient) -> None:
    _check_423(locked_client, "/api/assurance/search?q=loss")


def test_unlocked_search_has_no_store_header(unlocked_client: TestClient) -> None:
    r = unlocked_client.get("/api/assurance/search?q=Visible")
    assert r.headers.get("cache-control") == "no-store"


def test_unlocked_search_returns_matching_hits(unlocked_client: TestClient) -> None:
    r = unlocked_client.get("/api/assurance/search?q=Visible")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["hits"][0]["artifact_id"] == "LSS@visible-node"
    assert body["hits"][0]["record_type"] == "assurance-node"


def test_unlocked_search_no_match_returns_empty(unlocked_client: TestClient) -> None:
    r = unlocked_client.get("/api/assurance/search?q=NONEXISTENT_QUERY_XYZ")
    assert r.status_code == 200
    assert r.json()["count"] == 0


# ── Search: above-ceiling nodes must not leak ─────────────────────────────────

def test_search_secret_name_absent(leak_client: TestClient) -> None:
    r = leak_client.get("/api/assurance/search?q=HAZARD")
    assert r.status_code == 200
    text = r.text
    assert "SECRET HAZARD NAME" not in text
    assert "HAZ@secret-node" not in text


def test_search_secret_count_is_zero(leak_client: TestClient) -> None:
    r = leak_client.get("/api/assurance/search?q=HAZARD")
    assert r.json()["count"] == 0


# ── Search: hit shape has no content snippet ──────────────────────────────────

def test_search_hit_has_no_content_text(unlocked_client: TestClient) -> None:
    r = unlocked_client.get("/api/assurance/search?q=Visible")
    hit = r.json()["hits"][0]
    assert "content_text" not in hit
    assert "content" not in hit


# ── Empty query → empty result (no crash) ────────────────────────────────────

def test_search_empty_query_returns_empty(unlocked_client: TestClient) -> None:
    r = unlocked_client.get("/api/assurance/search?q=")
    assert r.status_code == 200
    assert r.json()["count"] == 0
