"""HTTP contract tests for the assurance analysis aggregate endpoints (WU-G5-P3).

Covers create/list/get/update, locked semantics, invalid input, optional anchor,
analysis-scoped node listing, and TLP exposure filtering (omit from lists +
indistinguishable 404 on direct read).
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.infrastructure.assurance._analysis_records import as_analysis_record
from src.infrastructure.gui.routers._assurance_analysis_routes import analysis_router
from src.infrastructure.gui.routers._assurance_read import read_router
from tests.support.api_app import build_api_app


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
        # Through `as_analysis_record`, so the fake is held to the same record shape every real
        # backend is. It used to omit `group_id`, `created_at` and `updated_at`, which let these
        # tests pass against a record no store would ever return — and the id stays predictable,
        # which is the only reason the fake exists rather than a real store.
        self._analyses[aid] = as_analysis_record({
            "analysis_id": aid, "group_id": None, "name": name, "method": method,
            "architecture_anchor_id": architecture_anchor_id, "status": status, "tlp": tlp,
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        })
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
    app = build_api_app(analysis_router, read_router)
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


def test_create_analysis_invalid_method_is_a_422(monkeypatch: pytest.MonkeyPatch) -> None:
    """422, not 400: a rejected parameter value is what `validation_error` is for, and the field path
    travels in `details` so a client can highlight the input rather than parse the sentence."""
    ctx = _FakeContext(_FakeStore())
    resp = _client(ctx, monkeypatch).post("/api/assurance/analyses", json={"name": "x", "method": "HAZOP"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "validation_error"
    assert detail["details"]["field_errors"][0]["field"] == "method"


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
    resp = _client(ctx, monkeypatch).get("/api/assurance/guidance/stpa-losses")
    assert resp.status_code == 200
    assert resp.json()["topic"] == "stpa-losses"


def test_guidance_unknown_topic_lists_available(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore())
    body = _client(ctx, monkeypatch).get("/api/assurance/guidance/zzz").json()
    assert "available_topics" in body


def test_completeness_answers_for_the_analysis_own_method(monkeypatch: pytest.MonkeyPatch) -> None:
    """One route, and the *analysis* decides which report it gets.

    Four routes used to answer this, each taking the analysis as an optional query parameter, so
    asking for a CAST report about an STPA analysis returned an empty one that read like a pass.
    """
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Brakes", "STPA")
    store.add_node(aid)
    resp = client.get(f"/api/assurance/analyses/{aid}/completeness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == "STPA"
    assert "passed" in body
    assert "checks" in body
    # The argument case travels with it: it is a second view of the same analysis, not a second
    # resource, which is what let `gsn/completeness` collapse in here too.
    assert "case" in body


def test_gsn_draft_is_analysis_scoped_and_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Brakes", "STPA", tlp="TLP:GREEN")
    store._nodes["L@1"] = {
        "node_id": "L@1", "node_type": "loss", "name": "Loss of control",
        "analysis_id": aid, "tlp": "TLP:AMBER",
    }
    body = client.get(f"/api/assurance/analyses/{aid}/gsn/draft").json()
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
    body = client.get(f"/api/assurance/analyses/{aid}/gsn/draft").json()
    assert body["visibility_limited"] is True
    assert body["publishable"] is False
    assert "Secret loss" not in str(body)


def test_the_argument_case_completeness_travels_with_the_method_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Brakes", "STPA")
    response = client.get(f"/api/assurance/analyses/{aid}/completeness")
    assert response.status_code == 200
    assert response.json()["case"]["passed"] is True


def test_completeness_of_a_method_without_one_is_a_typed_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An FMEA's projection is its matrix, so a completeness report of one does not exist.

    409, not 404 and not an empty report: the analysis is there and readable, and an empty report
    would read as a clean bill of health for a check that was never run.
    """
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Pump failure modes", "FMEA")
    response = client.get(f"/api/assurance/analyses/{aid}/completeness")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "analysis_method_mismatch"
    assert detail["details"]["actual_method"] == "FMEA"


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
    response = client.post(f"/api/assurance/analyses/{aid}/gsn/publications", json={
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
    response = client.post(f"/api/assurance/analyses/{aid}/gsn/publications", json={
        "diagram_id": "GSN@1.case",
        "source_bindings": [{"assurance_node_id": "H@1", "gsn_node_id": "G-H@1"}],
    })
    assert response.status_code == 200
    assert response.json()["binding_count"] == 1
    assert ctx.archive.ops == ["PUBLISH_GSN"]


def test_completeness_of_a_locked_store_is_423(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(_FakeStore(), available=False)
    resp = _client(ctx, monkeypatch).get("/api/assurance/analyses/AN@any/completeness")
    assert resp.status_code == 423


def test_grc_completeness_is_the_grc_report(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Q3 controls", "GRC")
    resp = client.get(f"/api/assurance/analyses/{aid}/completeness")
    assert resp.status_code == 200
    body = resp.json()
    assert "passed" in body
    assert set(body["checks"]) == {
        "obligation_has_constraint", "risk_has_treatment", "risk_has_owner",
    }


def test_cast_completeness_is_the_cast_report(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeStore()
    ctx = _FakeContext(store)
    client = _client(ctx, monkeypatch)
    aid = store.create_analysis("Incident review", "CAST")
    resp = client.get(f"/api/assurance/analyses/{aid}/completeness")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["checks"]) == {
        "baseline_exists", "incident_has_investigates", "corrective_action_derives_constraint",
    }
