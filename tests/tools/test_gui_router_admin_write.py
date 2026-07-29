"""Tests for the GUI admin router write endpoints.

Covers: 403 from _require_admin() for all write endpoints,
dry_run create/edit/delete entity, dry_run add/remove connection,
dry_run create/delete diagram — all in admin mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.admin import router as admin_router

httpx = pytest.importorskip("httpx")


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


ENT_ID = "REQ@1000000070.EntAdm.admin-entity"
TGT_ID = "REQ@1000000071.TgtAdm.admin-target"


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

Admin entity for testing.

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


def _outgoing_md(source: str, target: str) -> str:
    return f"""\
---
source-entity: {source}
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §connections -->

### archimate-association → {target}

Admin connection for testing.
"""


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def enterprise_root(tmp_path: Path) -> Path:
    root = tmp_path / "enterprise-repository"
    model_dir = root / "model" / "motivation" / "requirement"
    _write(model_dir / f"{ENT_ID}.md", _entity_md(ENT_ID, "Admin Entity"))
    _write(model_dir / f"{TGT_ID}.md", _entity_md(TGT_ID, "Admin Target"))
    _write(model_dir / f"{ENT_ID}.outgoing.md", _outgoing_md(ENT_ID, TGT_ID))
    return root


@pytest.fixture()
def non_admin_client(tmp_path: Path):
    """Client with admin_mode=False — all write endpoints return 403."""
    from starlette.testclient import TestClient

    root = tmp_path / "engagements" / "ENG-NA" / "architecture-repository"
    root.mkdir(parents=True)
    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


@pytest.fixture()
def admin_client(tmp_path: Path, enterprise_root: Path):
    """Client with admin_mode=True and enterprise root configured."""
    from starlette.testclient import TestClient

    eng = tmp_path / "engagements" / "ENG-ADM" / "architecture-repository"
    eng.mkdir(parents=True)
    repo = ArtifactRepository(shared_artifact_index([enterprise_root]))
    gui_state.init_state(repo, eng, enterprise_root, admin_mode=True)
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


# ── 403 for non-admin clients ─────────────────────────────────────────────────


class TestNonAdminReturns403:
    def test_create_entity_403(self, non_admin_client) -> None:
        r = non_admin_client.post(
            "/admin/api/entity",
            json={"artifact_type": "requirement", "name": "Test"},
        )
        assert r.status_code == 403

    def test_edit_entity_403(self, non_admin_client) -> None:
        r = non_admin_client.post(
            "/admin/api/entity/edit",
            json={"artifact_id": ENT_ID},
        )
        assert r.status_code == 403

    def test_remove_entity_403(self, non_admin_client) -> None:
        r = non_admin_client.post(
            "/admin/api/entity/remove",
            json={"artifact_id": ENT_ID},
        )
        assert r.status_code == 403

    def test_add_connection_403(self, non_admin_client) -> None:
        r = non_admin_client.post(
            "/admin/api/connection",
            json={
                "source_entity": ENT_ID,
                "connection_type": "archimate-association",
                "target_entity": TGT_ID,
            },
        )
        assert r.status_code == 403

    def test_remove_connection_403(self, non_admin_client) -> None:
        r = non_admin_client.post(
            "/admin/api/connection/remove",
            json={
                "source_entity": ENT_ID,
                "connection_type": "archimate-association",
                "target_entity": TGT_ID,
            },
        )
        assert r.status_code == 403

    def test_create_diagram_403(self, non_admin_client) -> None:
        r = non_admin_client.post(
            "/admin/api/diagram",
            json={
                "diagram_type": "archimate-application",
                "name": "Test",
                "entity_ids": [],
                "connection_ids": [],
            },
        )
        assert r.status_code == 403

    def test_remove_diagram_403(self, non_admin_client) -> None:
        r = non_admin_client.post(
            "/admin/api/diagram/remove",
            json={"artifact_id": "DIAG@1.AA.test"},
        )
        assert r.status_code == 403


# ── admin create entity ───────────────────────────────────────────────────────


class TestAdminCreateEntity:
    def test_dry_run_returns_not_wrote(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/entity",
            json={"artifact_type": "requirement", "name": "New Admin Entity", "dry_run": True},
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is False

    def test_dry_run_includes_artifact_id(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/entity",
            json={"artifact_type": "requirement", "name": "Named Entity", "dry_run": True},
        )
        assert r.status_code == 200
        assert r.json()["artifact_id"]

    def test_invalid_artifact_type_returns_400(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/entity",
            json={"artifact_type": "no-such-type", "name": "Bad Type", "dry_run": True},
        )
        assert r.status_code == 400


# ── admin edit entity ─────────────────────────────────────────────────────────


class TestAdminEditEntity:
    def test_dry_run_returns_not_wrote(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/entity/edit",
            json={"artifact_id": ENT_ID, "name": "Updated Name", "dry_run": True},
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is False

    def test_not_found_returns_400(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/entity/edit",
            json={"artifact_id": "REQ@9.ZZZ.no-such", "dry_run": True},
        )
        assert r.status_code == 400


# ── admin remove entity ───────────────────────────────────────────────────────


class TestAdminRemoveEntity:
    def test_dry_run_returns_not_wrote(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/entity/remove",
            json={"artifact_id": ENT_ID, "dry_run": True},
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is False

    def test_not_found_returns_400(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/entity/remove",
            json={"artifact_id": "REQ@9.ZZZ.no-such", "dry_run": True},
        )
        assert r.status_code == 400


# ── admin add connection ──────────────────────────────────────────────────────


class TestAdminAddConnection:
    def test_dry_run_returns_not_wrote(self, admin_client) -> None:
        # Use TGT→ENT direction — no outgoing file for TGT_ID
        r = admin_client.post(
            "/admin/api/connection",
            json={
                "source_entity": TGT_ID,
                "connection_type": "archimate-association",
                "target_entity": ENT_ID,
                "dry_run": True,
            },
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is False

    def test_unknown_source_returns_400(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/connection",
            json={
                "source_entity": "REQ@9.ZZZ.no-such",
                "connection_type": "archimate-association",
                "target_entity": ENT_ID,
                "dry_run": True,
            },
        )
        assert r.status_code == 400


# ── admin remove connection ───────────────────────────────────────────────────


class TestAdminRemoveConnection:
    def test_dry_run_returns_not_wrote(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/connection/remove",
            json={
                "source_entity": ENT_ID,
                "connection_type": "archimate-association",
                "target_entity": TGT_ID,
                "dry_run": True,
            },
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is False

    def test_connection_not_found_returns_400(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/connection/remove",
            json={
                "source_entity": ENT_ID,
                "connection_type": "archimate-association",
                "target_entity": "REQ@9.ZZZ.nonexistent",
                "dry_run": True,
            },
        )
        assert r.status_code == 400


# ── admin create diagram ──────────────────────────────────────────────────────


class TestAdminCreateDiagram:
    def test_dry_run_returns_not_wrote(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/diagram",
            json={
                "diagram_type": "archimate-application",
                "name": "Admin Test Diagram",
                "entity_ids": [],
                "connection_ids": [],
                "dry_run": True,
            },
        )
        assert r.status_code == 200
        assert r.json()["wrote"] is False

    def test_dry_run_includes_artifact_id(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/diagram",
            json={
                "diagram_type": "archimate-application",
                "name": "Named Diagram",
                "entity_ids": [],
                "connection_ids": [],
                "dry_run": True,
            },
        )
        assert r.status_code == 200
        assert r.json()["artifact_id"]


# ── admin remove diagram ──────────────────────────────────────────────────────


class TestAdminRemoveDiagram:
    def test_diagram_not_found_returns_400(self, admin_client) -> None:
        r = admin_client.post(
            "/admin/api/diagram/remove",
            json={"artifact_id": "DIAG@9.ZZZ.no-such-diag", "dry_run": True},
        )
        assert r.status_code == 400
