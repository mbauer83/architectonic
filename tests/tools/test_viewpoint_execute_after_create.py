"""Regression coverage: an engagement-repo viewpoint definition created through the GUI
authoring endpoint must be immediately executable by slug in the same process — no
dependency override, no restart. `execute_viewpoint`/`execute_viewpoint_projection`/
`execute_viewpoint_diagram`/`get_diagram_viewpoint_projection` previously read `viewpoints`
from a `RuntimeCatalogs` snapshot frozen at process startup, so a definition written
through `viewpoint_authoring.py` (which already read/wrote fresh per request) could never
be found by slug until the process restarted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_repository import ArtifactRepository
from src.infrastructure.app_bootstrap import install_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.viewpoint_authoring import router as viewpoint_authoring_router
from src.infrastructure.gui.routers.viewpoints import router as viewpoints_router

httpx = pytest.importorskip("httpx")


@pytest.fixture()
def engagement_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture()
def client(engagement_root: Path):
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([engagement_root]))
    gui_state.init_state(repo, engagement_root, None)
    app = FastAPI()
    install_module_registry(app)
    app.include_router(viewpoint_authoring_router)
    app.include_router(viewpoints_router)
    return TestClient(app)


def test_a_freshly_created_definition_executes_by_slug_without_a_restart(client) -> None:
    definition = {"slug": "just-created", "version": 1, "name": "Just Created"}
    create_resp = client.post("/api/viewpoints", json={"definition": definition, "dry_run": False})
    assert create_resp.json()["ok"] is True, create_resp.json()

    execute_resp = client.post("/api/viewpoints/execute", json={"slug": "just-created"})
    assert execute_resp.status_code == 200, execute_resp.json()
    assert execute_resp.json()["slug"] == "just-created"


def test_a_semantic_edit_is_visible_to_the_very_next_execution(client) -> None:
    definition = {"slug": "edited", "version": 1, "name": "Edited"}
    client.post("/api/viewpoints", json={"definition": definition, "dry_run": False})

    edited = {
        **definition, "version": 2,
        "scope": {"entity_types": ["application-component"]},
    }
    edit_resp = client.post("/api/viewpoints/edit", json={"definition": edited, "dry_run": False})
    assert edit_resp.json()["ok"] is True, edit_resp.json()

    execute_resp = client.post("/api/viewpoints/execute", json={"slug": "edited"})
    assert execute_resp.status_code == 200, execute_resp.json()
    assert execute_resp.json()["version"] == 2
