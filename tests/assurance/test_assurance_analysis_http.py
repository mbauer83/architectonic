"""HTTP contract tests for the assurance analysis aggregate endpoints (WU-G5-P3).

Covers create/list/get/update, locked semantics, invalid input, optional anchor,
analysis-scoped node listing, and TLP exposure filtering (omit from lists +
indistinguishable 404 on direct read).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.infrastructure.gui.routers._assurance_analysis_routes import analysis_router
from src.infrastructure.gui.routers._assurance_read import read_router


class _FakeStore:
    def __init__(self) -> None:
        self._analyses: dict[str, dict[str, Any]] = {}
        self._nodes: dict[str, dict[str, Any]] = {}
        self._n = 0

    def is_unlocked(self) -> bool:
        return True

    # analyses
    def create_analysis(self, name: str, method: str, architecture_anchor_id: str = "",
                        *, tlp: str = "TLP:WHITE", status: str = "draft") -> str:
        self._n += 1
        aid = f"{method}@{self._n}"
        self._analyses[aid] = {
            "analysis_id": aid, "name": name, "method": method,
            "architecture_anchor_id": architecture_anchor_id, "status": status, "tlp": tlp,
        }
        return aid

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        return self._analyses.get(analysis_id)

    def list_analyses(self, *, method: str | None = None,
                     status: str | None = None) -> list[dict[str, Any]]:
        out = list(self._analyses.values())
        if method:
            out = [a for a in out if a["method"] == method]
        if status:
            out = [a for a in out if a["status"] == status]
        return out

    def update_analysis(self, analysis_id: str, **attrs: Any) -> None:
        self._analyses[analysis_id].update(attrs)

    # nodes (for analysis-scoped count)
    def add_node(self, analysis_id: str, tlp: str = "TLP:WHITE") -> None:
        self._n += 1
        nid = f"N@{self._n}"
        self._nodes[nid] = {"node_id": nid, "node_type": "hazard", "tlp": tlp,
                            "analysis_id": analysis_id}

    def list_nodes(self, *, analysis_id: str | None = None, **_kw: Any) -> list[dict[str, Any]]:
        return [n for n in self._nodes.values()
                if analysis_id is None or n.get("analysis_id") == analysis_id]

    def list_edges(self, **_kw: Any) -> list[dict[str, Any]]:
        return []

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def register_arch_ref(self, assurance_node_id: str, arch_artifact_id: str, ref_type: str) -> None:
        self._nodes[assurance_node_id].setdefault("arch_refs", []).append({
            "arch_artifact_id": arch_artifact_id,
            "ref_type": ref_type,
        })

    def list_arch_refs(self, **_kw: Any) -> list[dict[str, Any]]:
        return []


class _FakeArchive:
    def __init__(self) -> None:
        self.ops: list[str] = []

    def append(self, operation: str, **_kw: Any) -> dict[str, Any]:
        self.ops.append(operation)
        return {"operation": operation}

    def list_baselines(self) -> list[dict[str, Any]]:
        return []


class _FakeContext:
    def __init__(self, store: _FakeStore, *, ceiling: str = "TLP:RED",
                 available: bool = True) -> None:
        self.store = store
        self.archive = _FakeArchive()
        self._ceiling = ceiling
        self._available = available

    @property
    def max_classification(self) -> str:
        return self._ceiling

    def is_available(self) -> bool:
        return self._available


_HTTP_CTX = "src.infrastructure.gui.routers._assurance_http.get_assurance_context"
_READ_POLICY = "src.infrastructure.gui.routers._assurance_read._policy"


def _client(ctx: _FakeContext, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a client with both route-module context lookups pointed at ``ctx``.

    Uses monkeypatch (auto-reverted after each test) so patches never leak into
    other tests sharing the same worker process.
    """
    app = FastAPI()
    app.include_router(analysis_router)
    app.include_router(read_router)
    monkeypatch.setattr(_HTTP_CTX, lambda: ctx)
    monkeypatch.setattr(
        _READ_POLICY,
        lambda: (ctx, AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())),
    )
    return TestClient(app, raise_server_exceptions=False)


# ── create ──────────────────────────────────────────────────────────────────────


def test_create_analysis_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore())
    resp = _client(ctx, monkeypatch).post("/api/assurance/analyses", json={
        "name": "Brakes", "method": "STPA", "architecture_anchor_id": "APP@1",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == "STPA"
    assert body["architecture_anchor_id"] == "APP@1"
    assert ctx.archive.ops == ["CREATE_ANALYSIS"]


def test_create_analysis_anchor_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore())
    resp = _client(ctx, monkeypatch).post("/api/assurance/analyses", json={"name": "Q3", "method": "GRC"})
    assert resp.status_code == 200
    assert resp.json()["architecture_anchor_id"] == ""


def test_create_analysis_invalid_method_400(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore())
    resp = _client(ctx, monkeypatch).post("/api/assurance/analyses", json={"name": "x", "method": "HAZOP"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_method"


def test_create_analysis_locked_423(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore(), available=False)
    resp = _client(ctx, monkeypatch).post("/api/assurance/analyses", json={"name": "x", "method": "STPA"})
    assert resp.status_code == 423


# ── list / get / update ──────────────────────────────────────────────────────────


def test_list_and_get_and_node_count(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Brakes", "STPA", "APP@1")
    store.add_node(aid)
    store.add_node(aid)
    listed = client.get("/api/assurance/analyses").json()
    assert listed["count"] == 1
    detail = client.get(f"/api/assurance/analyses/{aid}").json()
    assert detail["analysis"]["analysis_id"] == aid
    assert detail["node_count"] == 2


def test_get_missing_analysis_404(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore())
    assert _client(ctx, monkeypatch).get("/api/assurance/analyses/NOPE@1").status_code == 404


def test_update_analysis_status(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Brakes", "STPA")
    resp = client.patch(f"/api/assurance/analyses/{aid}", json={"status": "active"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_list_locked_423(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore(), available=False)
    assert _client(ctx, monkeypatch).get("/api/assurance/analyses").status_code == 423


# ── exposure (TLP ceiling) ───────────────────────────────────────────────────────


def test_above_ceiling_analysis_omitted_from_list(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store, ceiling="TLP:GREEN")
    client = _client(ctx, monkeypatch)
    store.create_analysis("low", "STPA", tlp="TLP:GREEN")
    store.create_analysis("secret", "STPA", tlp="TLP:RED")
    body = client.get("/api/assurance/analyses").json()
    assert body["count"] == 1
    assert body["analyses"][0]["name"] == "low"
    assert body["visibility_limited"] is True


def test_above_ceiling_analysis_direct_read_404(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store, ceiling="TLP:GREEN")
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("secret", "STPA", tlp="TLP:RED")
    # Indistinguishable from absent.
    assert client.get(f"/api/assurance/analyses/{aid}").status_code == 404


@pytest.mark.parametrize("scoped,expected", [("A@1", 1), ("A@2", 0)])
def test_node_listing_is_analysis_scoped(scoped: str, expected: int, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    store._analyses["A@1"] = {"analysis_id": "A@1", "tlp": "TLP:WHITE"}
    store.add_node("A@1")
    resp = client.get(f"/api/assurance/nodes?analysis_id={scoped}")
    assert resp.status_code == 200
    assert resp.json()["count"] == expected


# ── method support (guidance + stpa-complete) ────────────────────────────────────


def test_guidance_returns_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    # Guidance is static and always callable (works even when locked).
    ctx = _FakeContext(_FakeStore(), available=False)
    resp = _client(ctx, monkeypatch).get("/api/assurance/guidance?topic=stpa-losses")
    assert resp.status_code == 200
    assert resp.json()["topic"] == "stpa-losses"


def test_guidance_unknown_topic_lists_available(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore())
    body = _client(ctx, monkeypatch).get("/api/assurance/guidance?topic=zzz").json()
    assert "available_topics" in body


def test_stpa_complete_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Brakes", "STPA")
    store.add_node(aid)
    resp = client.get(f"/api/assurance/stpa-complete?analysis_id={aid}")
    assert resp.status_code == 200
    body = resp.json()
    assert "passed" in body
    assert "checks" in body


def test_gsn_draft_is_analysis_scoped_and_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Brakes", "STPA", tlp="TLP:GREEN")
    store._nodes["L@1"] = {
        "node_id": "L@1", "node_type": "loss", "name": "Loss of control",
        "analysis_id": aid, "tlp": "TLP:AMBER",
    }
    body = client.get(f"/api/assurance/gsn/draft?analysis_id={aid}").json()
    assert body["effective_tlp"] == "TLP:AMBER"
    assert body["publishable"] is False
    assert body["draft"]["top_goal"]["source_losses"] == ["L@1"]
    assert body["diagram_entities"]["nodes"][0]["gsn_type"] == "goal"


def test_gsn_draft_omits_above_ceiling_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store, ceiling="TLP:GREEN")
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Brakes", "STPA", tlp="TLP:GREEN")
    store._nodes["L@secret"] = {
        "node_id": "L@secret", "node_type": "loss", "name": "Secret loss",
        "analysis_id": aid, "tlp": "TLP:RED",
    }
    body = client.get(f"/api/assurance/gsn/draft?analysis_id={aid}").json()
    assert body["visibility_limited"] is True
    assert body["publishable"] is False
    assert "Secret loss" not in str(body)


def test_gsn_completeness_is_analysis_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Brakes", "STPA")
    response = client.get(f"/api/assurance/gsn/completeness?analysis_id={aid}")
    assert response.status_code == 200
    assert response.json()["passed"] is True


def test_gsn_publication_rejects_confidential_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Repo:
        def get_diagram(self, _diagram_id: str) -> object:
            return object()

    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Secret", "STPA", tlp="TLP:AMBER")
    monkeypatch.setattr(
        "src.infrastructure.gui.routers.state.get_repo",
        lambda: _Repo(),
    )
    response = client.post("/api/assurance/gsn/publications", json={
        "analysis_id": aid,
        "diagram_id": "GSN@1.case",
        "source_bindings": [],
    })
    assert response.status_code == 409
    assert response.json()["error"] == "classification_not_publishable"


def test_gsn_publication_records_bindings_and_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Repo:
        def get_diagram(self, _diagram_id: str) -> object:
            return object()

    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Cleared", "STPA", tlp="TLP:GREEN")
    store._nodes["H@1"] = {
        "node_id": "H@1", "node_type": "hazard", "name": "Hazard",
        "analysis_id": aid, "tlp": "TLP:GREEN",
    }
    monkeypatch.setattr("src.infrastructure.gui.routers.state.get_repo", lambda: _Repo())
    response = client.post("/api/assurance/gsn/publications", json={
        "analysis_id": aid,
        "diagram_id": "GSN@1.case",
        "source_bindings": [{"assurance_node_id": "H@1", "gsn_node_id": "G-H@1"}],
    })
    assert response.status_code == 200
    assert response.json()["binding_count"] == 1
    assert ctx.archive.ops == ["PUBLISH_GSN"]


def test_stpa_complete_locked_423(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore(), available=False)
    assert _client(ctx, monkeypatch).get("/api/assurance/stpa-complete").status_code == 423


def test_grc_complete_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Q3 controls", "GRC")
    resp = client.get(f"/api/assurance/grc-complete?analysis_id={aid}")
    assert resp.status_code == 200
    body = resp.json()
    assert "passed" in body
    assert set(body["checks"]) == {
        "obligation_has_constraint", "risk_has_treatment", "risk_has_owner",
    }


def test_grc_complete_locked_423(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore(), available=False)
    assert _client(ctx, monkeypatch).get("/api/assurance/grc-complete").status_code == 423


def test_cast_complete_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Incident review", "CAST")
    resp = client.get(f"/api/assurance/cast-complete?analysis_id={aid}")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["checks"]) == {
        "baseline_exists", "incident_has_investigates", "corrective_action_derives_constraint",
    }


def test_cast_complete_locked_423(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore(), available=False)
    assert _client(ctx, monkeypatch).get("/api/assurance/cast-complete").status_code == 423
