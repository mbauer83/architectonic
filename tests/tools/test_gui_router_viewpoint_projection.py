"""Tests for GET /api/diagrams/{id}/viewpoint-projection: the GUI ghost/hide overlay's data
source — read-only REST wrapper around ``project_artifact_by_frontmatter``, the second
consumer of the projection service.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_repository import ArtifactRepository
from src.domain.concept_scope import ConceptScope
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.viewpoints import router as viewpoints_router

httpx = pytest.importorskip("httpx")

STK_ID = "STK@1000000051.EntSch.projection-stakeholder"
DIAGRAM_ID = "ARC@1000000052.EntSch.projection-diagram"
NO_VIEWPOINT_DIAGRAM_ID = "ARC@1000000053.EntSch.no-viewpoint-diagram"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _stakeholder_md() -> str:
    return f"""\
---
artifact-id: {STK_ID}
artifact-type: stakeholder
name: "Projection Stakeholder"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## Projection Stakeholder

Test stakeholder for the viewpoint-projection endpoint.
"""


def _diagram_md(artifact_id: str, *, viewpoint_block: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: archimate-motivation
name: "Projection Diagram"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
entity-ids-used: [{STK_ID}]
connection-ids-used: []
{viewpoint_block}---
@startuml {artifact_id}
title Projection Diagram
@enduml
"""


@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-VPP" / "architecture-repository"
    _write(root / "model" / "motivation" / "stakeholder" / f"{STK_ID}.md", _stakeholder_md())
    _write(
        root / "diagram-catalog" / "diagrams" / f"{DIAGRAM_ID}.puml",
        _diagram_md(DIAGRAM_ID, viewpoint_block="viewpoint: {slug: proj-test, version: 2}\n"),
    )
    _write(
        root / "diagram-catalog" / "diagrams" / f"{NO_VIEWPOINT_DIAGRAM_ID}.puml",
        _diagram_md(NO_VIEWPOINT_DIAGRAM_ID, viewpoint_block=""),
    )
    return root


@pytest.fixture()
def client(populated_root: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.rest.routers.viewpoints import fresh_viewpoints_runtime_catalogs_dependency

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    catalogs = build_runtime_catalogs(get_module_registry())
    definition = ViewpointDefinition(
        slug="proj-test", version=3, name="Projection Test", scope=ConceptScope.unrestricted()
    )
    catalogs = dataclasses.replace(catalogs, viewpoints=ViewpointCatalog(entries=(definition,)))

    app = FastAPI()
    app.dependency_overrides[fresh_viewpoints_runtime_catalogs_dependency] = lambda: catalogs
    app.include_router(viewpoints_router)
    return TestClient(app)


class TestNoApplication:
    def test_diagram_without_viewpoint_is_not_applied(self, client) -> None:
        resp = client.get(f"/api/diagrams/{NO_VIEWPOINT_DIAGRAM_ID}/viewpoint-projection")
        assert resp.status_code == 200
        assert resp.json() == {"applied": False}


class TestApplication:
    def test_returns_projection_with_placed_entity_and_stale_pin(self, client) -> None:
        resp = client.get(f"/api/diagrams/{DIAGRAM_ID}/viewpoint-projection")
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied"] is True
        assert body["target"] == "diagram"
        assert body["stale_pin"] is True  # pinned 2 < current definition version 3
        items = {item["item_id"]: item for item in body["items"]}
        assert items[STK_ID]["item_kind"] == "entity"
        assert items[STK_ID]["reasons"] == []


class TestUnknownDiagram:
    def test_missing_diagram_is_404(self, client) -> None:
        resp = client.get("/api/diagrams/ARC@0000000000.xxxxxx.missing/viewpoint-projection")
        assert resp.status_code == 404
