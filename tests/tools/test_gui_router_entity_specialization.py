"""REST-level round-trip for the `specialization` field on POST /api/entities and
PATCH /api/entities/{artifact_id} — proves the GUI (a REST-only client) can set and clear an entity's
specialization, not just the MCP tools and the underlying application functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.entities import router as entities_router
from tests.support.api_app import build_api_app

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
    app = build_api_app(entities_router)
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
        r = client.post("/api/entities", json=payload)
        # A committed create answers 201 and names the resource in Location.
        assert r.status_code == 201
        assert r.headers["Location"] == f"/api/entities/{r.json()['artifact_id']}"
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
        created = client.post("/api/entities", json=create_payload).json()
        artifact_id = created["artifact_id"]

        r = client.patch(
            f"/api/entities/{artifact_id}",
            json={"specialization": "constraint", "dry_run": False},
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is True
        written = next(root.rglob(f"{artifact_id}.md"))
        assert "specialization: constraint" in written.read_text(encoding="utf-8")

        r = client.patch(
            f"/api/entities/{artifact_id}",
            json={"specialization": "", "dry_run": False},
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is True
        assert "specialization:" not in written.read_text(encoding="utf-8")
