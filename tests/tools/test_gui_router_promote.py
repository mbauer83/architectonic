"""Tests for the GUI promote router.

Covers: POST /api/promote/plan (error cases + valid plan),
POST /api/promote/execute (error case + dry_run early-return).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.app_bootstrap import install_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.promote import router as promote_router

httpx = pytest.importorskip("httpx")


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


ENT_ID = "REQ@1000000060.EntPrm.promote-entity"


def _entity_md(artifact_id: str, name: str) -> str:
    slug = artifact_id.split(".")[-1].replace("-", "_")
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

Promote entity for testing.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: REQ_{slug}
```
"""


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def eng_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-PRM" / "architecture-repository"
    _write(
        root / "model" / "motivation" / "requirement" / f"{ENT_ID}.md",
        _entity_md(ENT_ID, "Promote Entity"),
    )
    return root


@pytest.fixture()
def ent_root(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    root.mkdir(parents=True)
    return root


@pytest.fixture()
def no_enterprise_client(eng_root: Path):
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([eng_root]))
    gui_state.init_state(repo, eng_root, None)
    app = FastAPI()
    app.include_router(promote_router)
    install_module_registry(app)
    return TestClient(app)


@pytest.fixture()
def both_roots_client(eng_root: Path, ent_root: Path):
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([eng_root]))
    gui_state.init_state(repo, eng_root, ent_root)
    app = FastAPI()
    app.include_router(promote_router)
    install_module_registry(app)
    return TestClient(app)


# ── promote/plan errors ───────────────────────────────────────────────────────


class TestPromotePlanErrors:
    def test_no_enterprise_root_returns_500(self, no_enterprise_client) -> None:
        r = no_enterprise_client.post("/api/promote/plan", json={})
        assert r.status_code == 500

    def test_no_artifacts_selected_returns_400(self, both_roots_client) -> None:
        r = both_roots_client.post("/api/promote/plan", json={})
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "artifact" in detail.lower() or "selected" in detail.lower()

    def test_unknown_entity_returns_400(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/plan",
            json={"entity_ids": ["REQ@9.ZZZ.no-such-entity"]},
        )
        assert r.status_code == 400


# ── promote/plan happy path ───────────────────────────────────────────────────


class TestPromotePlan:
    def test_plan_with_valid_entity(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/plan",
            json={"entity_ids": [ENT_ID]},
        )
        assert r.status_code == 200
        data = r.json()
        assert "entities_to_add" in data
        assert "conflicts" in data
        assert "connection_ids" in data
        assert "already_in_enterprise" in data

    def test_entity_goes_to_entities_to_add(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/plan",
            json={"entity_ids": [ENT_ID]},
        )
        assert r.status_code == 200
        data = r.json()
        assert ENT_ID in data["entities_to_add"]

    def test_plan_with_entity_id_field(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/plan",
            json={"entity_id": ENT_ID},
        )
        assert r.status_code == 200

    def test_plan_response_has_warnings(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/plan",
            json={"entity_ids": [ENT_ID]},
        )
        assert r.status_code == 200
        assert "warnings" in r.json()

    def test_plan_response_has_schema_errors(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/plan",
            json={"entity_ids": [ENT_ID]},
        )
        assert r.status_code == 200
        assert "schema_errors" in r.json()

    def test_plan_response_has_structural_closure(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/plan",
            json={"entity_ids": [ENT_ID]},
        )
        assert r.status_code == 200
        assert r.json()["structural_closure"] == []

    def test_plan_response_has_missing_dependencies(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/plan",
            json={"entity_ids": [ENT_ID]},
        )
        assert r.status_code == 200
        assert r.json()["missing_dependencies"] == []


# ── promote/execute errors ────────────────────────────────────────────────────


class TestPromoteExecuteErrors:
    def test_no_enterprise_root_returns_500(self, no_enterprise_client) -> None:
        r = no_enterprise_client.post(
            "/api/promote/execute",
            json={"dry_run": True},
        )
        assert r.status_code == 500

    def test_no_artifacts_selected_returns_400(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/execute",
            json={"dry_run": True},
        )
        assert r.status_code == 400


# ── promote/execute dry_run ───────────────────────────────────────────────────


class TestPromoteExecuteDryRun:
    def test_dry_run_returns_not_executed(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/execute",
            json={"entity_ids": [ENT_ID], "dry_run": True},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["dry_run"] is True
        assert data["executed"] is False

    def test_dry_run_response_has_expected_keys(self, both_roots_client) -> None:
        r = both_roots_client.post(
            "/api/promote/execute",
            json={"entity_ids": [ENT_ID], "dry_run": True},
        )
        assert r.status_code == 200
        data = r.json()
        assert "copied_files" in data
        assert "updated_files" in data
        assert "verification_errors" in data
        assert "rolled_back" in data
