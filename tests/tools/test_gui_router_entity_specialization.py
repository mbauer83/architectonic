"""REST-level round-trip for the `specialization` field on POST /api/entity and
/api/entity/edit — proves the GUI (a REST-only client) can set and clear an entity's
specialization, not just the MCP tools and the underlying application functions."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.entities import router as entities_router

httpx = pytest.importorskip("httpx")


def _eng_root(tmp_path: Path) -> Path:
    return tmp_path / "engagements" / "ENG-ESPEC" / "architecture-repository"


@pytest.fixture()
def sync_client(tmp_path: Path):
    from starlette.testclient import TestClient

    root = _eng_root(tmp_path)
    root.mkdir(parents=True)
    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    app = FastAPI()
    app.include_router(entities_router)
    return TestClient(app), root


class TestCreateEntitySpecialization:
    def test_specialization_persists_in_frontmatter(self, sync_client) -> None:
        client, root = sync_client
        payload = {
            "artifact_type": "requirement",
            "name": "Espec Requirement",
            "specialization": "constraint",
            "dry_run": False,
        }
        r = client.post("/api/entity", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["wrote"] is True

        written = next(root.rglob(f"{data['artifact_id']}.md"))
        assert "specialization: constraint" in written.read_text(encoding="utf-8")


class TestEditEntitySpecialization:
    def test_specialization_set_then_cleared(self, sync_client) -> None:
        client, root = sync_client
        create_payload = {
            "artifact_type": "requirement",
            "name": "Espec Edit Requirement",
            "dry_run": False,
        }
        created = client.post("/api/entity", json=create_payload).json()
        artifact_id = created["artifact_id"]

        r = client.post(
            "/api/entity/edit",
            json={"artifact_id": artifact_id, "specialization": "constraint", "dry_run": False},
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is True
        written = next(root.rglob(f"{artifact_id}.md"))
        assert "specialization: constraint" in written.read_text(encoding="utf-8")

        r = client.post(
            "/api/entity/edit",
            json={"artifact_id": artifact_id, "specialization": "", "dry_run": False},
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is True
        assert "specialization:" not in written.read_text(encoding="utf-8")
