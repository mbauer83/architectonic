"""GET /api/backend-identity: realpath-normalized served repo roots + software version."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.entities import router as entities_router

httpx = pytest.importorskip("httpx")


def _client(eng_root: Path, ent_root: Path | None):
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([eng_root]))
    gui_state.init_state(repo, eng_root, ent_root)
    app = FastAPI()
    app.include_router(entities_router)
    return TestClient(app)


def test_backend_identity_reports_software_version(tmp_path: Path) -> None:
    eng_root = tmp_path / "engagement"
    eng_root.mkdir()
    client = _client(eng_root, None)

    resp = client.get("/api/backend-identity")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["software_version"], str)
    assert body["software_version"] != ""


def test_backend_identity_lists_both_roots_when_enterprise_configured(tmp_path: Path) -> None:
    eng_root = tmp_path / "engagement"
    ent_root = tmp_path / "enterprise"
    eng_root.mkdir()
    ent_root.mkdir()
    client = _client(eng_root, ent_root)

    body = client.get("/api/backend-identity").json()

    assert str(eng_root.resolve()) in body["repo_roots"]
    assert str(ent_root.resolve()) in body["repo_roots"]
    assert len(body["repo_roots"]) == 2


@pytest.mark.skipif(os.name == "nt", reason="symlink realpath normalization test is POSIX-oriented")
def test_backend_identity_realpath_normalizes_symlinked_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real-engagement"
    real_root.mkdir()
    linked_root = tmp_path / "linked-engagement"
    linked_root.symlink_to(real_root)
    client = _client(linked_root, None)

    body = client.get("/api/backend-identity").json()

    assert body["repo_roots"] == [str(real_root.resolve())]
    assert str(linked_root) not in body["repo_roots"]
