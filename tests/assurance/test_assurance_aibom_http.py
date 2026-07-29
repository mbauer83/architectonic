"""Tests for the AI-BOM HTTP read endpoints (scan / roles / export).

  - scan: un-gated; ranks public architecture model entities, excludes diagram-only
    nodes, honours the limit.
  - roles: un-gated; canonical AI-BOM role vocabulary (single backend source).
  - export: un-gated pure transform; emits CycloneDX 1.6 from caller-confirmed
    AI components; tolerates a malformed body.
  - Cache-Control: no-store on every response.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI

pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

_HTTP_CTX = "src.infrastructure.gui.routers._assurance_http.get_assurance_context"
_REPO = "src.infrastructure.gui.routers.state.maybe_get_repo"


class _FakeContext:
    def __init__(self, *, unlocked: bool = True, ceiling: str = "TLP:RED") -> None:
        self._unlocked = unlocked
        self.max_classification = ceiling

    def is_available(self) -> bool:
        return self._unlocked


@dataclass
class _FakeEntity:
    artifact_id: str
    name: str
    artifact_type: str
    content_text: str = ""
    host_diagram_id: str | None = None
    specializations: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)


class _FakeRepo:
    def __init__(self, entities: list[_FakeEntity], connections: list[Any] | None = None) -> None:
        self._entities = entities
        self._connections = connections or []

    def list_entities(self, *, domain: str | None = None, **_kwargs: Any) -> list[_FakeEntity]:
        return self._entities

    def list_connections(self, **_kwargs: Any) -> list[Any]:
        return self._connections


_ROOT = "src.infrastructure.gui.routers.state.maybe_engagement_root"


def _client(ctx: _FakeContext, monkeypatch: pytest.MonkeyPatch,
            repo: _FakeRepo | None = None, root: Any = None) -> TestClient:
    from src.infrastructure.gui.routers.assurance import router

    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr(_HTTP_CTX, lambda: ctx)
    if repo is not None:
        monkeypatch.setattr(_REPO, lambda: repo)
    monkeypatch.setattr(_ROOT, lambda: root)
    return TestClient(app, raise_server_exceptions=False)


# ── Scan ────────────────────────────────────────────────────────────────────

def test_scan_ranks_ai_entities_and_excludes_diagram_only(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _FakeRepo([
        _FakeEntity("APP@1", "Claude Inference Service", "application-component"),
        _FakeEntity("APP@2", "Billing Ledger", "application-component"),
        _FakeEntity("GSN@n", "LLM gateway node", "application-component", host_diagram_id="DGM@1"),
    ])
    ctx = _FakeContext(unlocked=True)
    r = _client(ctx, monkeypatch, repo=repo).get("/api/assurance/aibom/scan")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    body = r.json()
    ids = {c["entity_id"] for c in body["candidates"]}
    assert "APP@1" in ids  # AI name pattern matched
    assert "APP@2" not in ids  # no AI signal
    assert "GSN@n" not in ids  # diagram-only excluded despite AI name


def test_scan_honours_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _FakeRepo([
        _FakeEntity(f"APP@{i}", f"GPT model {i}", "application-component") for i in range(5)
    ])
    ctx = _FakeContext(unlocked=True)
    r = _client(ctx, monkeypatch, repo=repo).get("/api/assurance/aibom/scan?limit=2")
    assert r.json()["count"] == 2


def test_scan_no_repo_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(unlocked=True)
    monkeypatch.setattr(_REPO, lambda: None)
    r = _client(ctx, monkeypatch).get("/api/assurance/aibom/scan")
    assert r.status_code == 200
    assert r.json()["candidates"] == []


# ── Roles ─────────────────────────────────────────────────────────────────────

def test_roles_match_canonical_backend_source(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infrastructure.assurance._aibom_exporter import AI_BOM_ROLES

    ctx = _FakeContext(unlocked=True)
    r = _client(ctx, monkeypatch).get("/api/assurance/aibom/roles")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    # The endpoint is the single source the GUI consumes — it must mirror the exporter.
    assert r.json()["roles"] == list(AI_BOM_ROLES)


# ── Export ────────────────────────────────────────────────────────────────────

def test_export_derives_the_mlbom_from_the_model(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # The export now DERIVES from the architecture model — an entity marked ai-model becomes
    # a machine-learning-model component; no caller-supplied component list.
    repo = _FakeRepo([
        _FakeEntity("APP@1.a.model", "Fraud Model", "application-component",
                    specializations=("ai-model",), attributes={"Task": "classification"}),
        _FakeEntity("APP@2.b.plain", "Billing", "application-component"),
    ])
    ctx = _FakeContext(unlocked=True)
    r = _client(ctx, monkeypatch, repo=repo, root=tmp_path).post(
        "/api/assurance/aibom/export", json={"notes": "draft ML-BOM"}
    )
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    body = r.json()
    assert body["component_count"] == 1  # only the AI-specialized entity
    assert body["bom"]["specVersion"] == "1.6"
    assert body["bom"]["components"][0]["type"] == "machine-learning-model"
    assert body["coverage"] is not None  # coverage rides along with the export


def test_export_no_repo_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _FakeContext(unlocked=True)
    monkeypatch.setattr(_REPO, lambda: None)
    r = _client(ctx, monkeypatch).post("/api/assurance/aibom/export", json={})
    assert r.status_code == 200
    assert r.json()["component_count"] == 0


def test_coverage_reports_gaps_over_the_model(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    repo = _FakeRepo([
        _FakeEntity("APP@1.a.model", "Fraud Model", "application-component", specializations=("ai-model",)),
    ])
    ctx = _FakeContext(unlocked=True)
    r = _client(ctx, monkeypatch, repo=repo, root=tmp_path).get("/api/assurance/aibom/coverage")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    body = r.json()
    report = next(c for c in body["components"] if c["entity_id"] == "APP@1.a.model")
    assert report["missing_dataset_linkage"] is True  # a model with no trained-on link
    assert report["missing_governance"] is True
