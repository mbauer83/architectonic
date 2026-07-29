"""Tests for the `viewpoint` parameter on the GUI diagram write endpoints (WU-E5a):
POST /api/diagram and POST /api/diagram/edit now accept a `viewpoint` mapping, threading
straight through to `create_diagram`/`edit_diagram` — the REST surface the diagram
create/edit views use to persist the viewpoint selector's choice, including clearing it
back to "none" (see tests/tools/test_diagram_edit_viewpoint_clear.py for the underlying
`edit_diagram` sentinel-fix unit coverage).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.diagrams import router as diagrams_router

httpx = pytest.importorskip("httpx")

STK_ID = "STK@1000000061.EntSch.viewpoint-write-stakeholder"


def _stakeholder_md() -> str:
    return f"""\
---
artifact-id: {STK_ID}
artifact-type: stakeholder
name: "Viewpoint Write Stakeholder"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## Viewpoint Write Stakeholder

Test stakeholder for the viewpoint write-endpoint tests.

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Stakeholder
label: "Viewpoint Write Stakeholder"
alias: STK_test
```
"""


@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-VPW" / "architecture-repository"
    model_dir = root / "model" / "motivation" / "stakeholder"
    model_dir.mkdir(parents=True)
    (model_dir / f"{STK_ID}.md").write_text(_stakeholder_md(), encoding="utf-8")
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture()
def sync_client(populated_root: Path):
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    app = FastAPI()
    app.include_router(diagrams_router)
    return TestClient(app)


def _fm(content: str) -> dict:
    return yaml.safe_load(content.split("---\n")[1])


def _create_body(*, viewpoint: dict[str, object] | None = None, dry_run: bool = True) -> dict[str, object]:
    body: dict[str, object] = {
        "diagram_type": "archimate-motivation",
        "name": "Landscape",
        "entity_ids": [STK_ID],
        "connection_ids": [],
        "dry_run": dry_run,
    }
    if viewpoint is not None:
        body["viewpoint"] = viewpoint
    return body


class TestCreateDiagramWithViewpoint:
    def test_create_persists_viewpoint(self, sync_client) -> None:
        r = sync_client.post("/api/diagram", json=_create_body(viewpoint={"slug": "motivation", "version": 1}))
        assert r.status_code == 200
        body = r.json()
        assert body["verification"]["valid"], body["verification"]
        assert _fm(body["content"])["viewpoint"] == {"slug": "motivation", "version": 1}

    def test_create_without_viewpoint_omits_it(self, sync_client) -> None:
        r = sync_client.post("/api/diagram", json=_create_body())
        assert r.status_code == 200
        body = r.json()
        assert body["verification"]["valid"], body["verification"]
        assert "viewpoint" not in _fm(body["content"])


class TestEditDiagramViewpoint:
    def _create(self, sync_client) -> str:
        r = sync_client.post(
            "/api/diagram", json=_create_body(viewpoint={"slug": "motivation", "version": 1}, dry_run=False)
        )
        body = r.json()
        assert body["wrote"], body
        return str(body["artifact_id"])

    def _edit_body(self, artifact_id: str, *, viewpoint: dict[str, object] | None) -> dict[str, object]:
        return {
            "artifact_id": artifact_id,
            "diagram_type": "archimate-motivation",
            "name": "Landscape",
            "entity_ids": [STK_ID],
            "connection_ids": [],
            "viewpoint": viewpoint,
            "dry_run": True,
        }

    def test_edit_clears_viewpoint_with_explicit_null(self, sync_client) -> None:
        artifact_id = self._create(sync_client)
        edit = sync_client.post("/api/diagram/edit", json=self._edit_body(artifact_id, viewpoint=None))
        assert edit.status_code == 200
        body = edit.json()
        assert body["verification"]["valid"], body["verification"]
        assert "viewpoint" not in _fm(body["content"])

    def test_edit_replaces_viewpoint(self, sync_client) -> None:
        artifact_id = self._create(sync_client)
        edit = sync_client.post(
            "/api/diagram/edit", json=self._edit_body(artifact_id, viewpoint={"slug": "layered", "version": 1})
        )
        assert edit.status_code == 200
        body = edit.json()
        assert body["verification"]["valid"], body["verification"]
        assert _fm(body["content"])["viewpoint"] == {"slug": "layered", "version": 1}
