"""Choosing where an artifact is filed, and moving it later, over the REST surface.

A model-project collection is an artifact's *home*: on disk it is `projects/<group>/model/…`, and
without one the artifact sits at the repository root. The write path has placed and moved artifacts
by group since groups existed, and every MCP twin offers it — but no REST write body carried the
field, so nothing a person could reach could choose a home or change one. Everything created through
the interface landed in `uncategorized` and only an agent could re-home it.

These assert the two halves per kind, and the third case is the one that makes the others mean
something: an edit that does not mention a home leaves the artifact where it is. Without it a
pass-through that moved everything to `uncategorized` on every save would pass the first two.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture()
def client(tmp_path: Path) -> Any:
    """An engagement repository and an app over the three write surfaces."""
    from starlette.testclient import TestClient

    from src.application.artifacts.query import ArtifactRepository
    from src.infrastructure.artifact_index import shared_artifact_index
    from src.infrastructure.rest.routers import documents as documents_router
    from src.infrastructure.rest.routers import state as gui_state
    from src.infrastructure.rest.routers.entities import router as entities_router
    from src.infrastructure.workspace.engagement_repo_template import ensure_arch_repo_defaults
    from tests.support.api_app import build_api_app

    root = tmp_path / "engagements" / "ENG-HOME" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    ensure_arch_repo_defaults(root)

    with shared_artifact_index([root]) as index:
        gui_state.init_state(ArtifactRepository(index), root, None, admin_mode=False)
        app = build_api_app(entities_router.router, documents_router.router)
        yield TestClient(app), root


def _created(response: Any) -> tuple[str, str]:
    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert body["wrote"], body
    return body["artifact_id"], body["path"]


class TestAnEntity:
    def test_it_is_created_in_the_home_that_was_chosen(self, client) -> None:  # noqa: ANN001
        api, root = client

        _id, path = _created(api.post("/api/entities", json={
            "artifact_type": "requirement", "name": "Filed Requirement",
            "group": "platform-core", "dry_run": False,
        }))

        assert Path(path).is_relative_to(root / "projects" / "platform-core")

    def test_no_home_chosen_leaves_it_outside_every_collection(self, client) -> None:  # noqa: ANN001
        api, root = client

        _id, path = _created(api.post("/api/entities", json={
            "artifact_type": "requirement", "name": "Unfiled Requirement", "dry_run": False,
        }))

        assert not Path(path).is_relative_to(root / "projects")

    def test_it_is_moved_by_naming_another_home(self, client) -> None:  # noqa: ANN001
        api, root = client
        artifact_id, _path = _created(api.post("/api/entities", json={
            "artifact_type": "requirement", "name": "Movable Requirement",
            "group": "platform-core", "dry_run": False,
        }))

        _id, moved = _created(api.patch(
            f"/api/entities/{artifact_id}", json={"group": "engineering-quality", "dry_run": False},
        ))

        assert Path(moved).is_relative_to(root / "projects" / "engineering-quality")

    def test_an_edit_that_says_nothing_about_its_home_does_not_move_it(self, client) -> None:  # noqa: ANN001
        """The case that makes the others mean something."""
        api, root = client
        artifact_id, _path = _created(api.post("/api/entities", json={
            "artifact_type": "requirement", "name": "Staying Put",
            "group": "platform-core", "dry_run": False,
        }))

        _id, after = _created(api.patch(
            f"/api/entities/{artifact_id}", json={"status": "active", "dry_run": False},
        ))

        assert Path(after).is_relative_to(root / "projects" / "platform-core")


class TestADocument:
    def test_it_is_created_in_the_home_that_was_chosen(self, client) -> None:  # noqa: ANN001
        api, root = client

        _id, path = _created(api.post("/api/documents", json={
            "doc_type": "adr", "title": "A Filed Decision",
            "group": "platform-core", "dry_run": False,
        }))

        assert Path(path).is_relative_to(root / "docs" / "adr" / "platform-core")

    def test_it_is_moved_by_naming_another_home(self, client) -> None:  # noqa: ANN001
        api, root = client
        artifact_id, _path = _created(api.post("/api/documents", json={
            "doc_type": "adr", "title": "A Movable Decision",
            "group": "platform-core", "dry_run": False,
        }))

        _id, moved = _created(api.patch(
            f"/api/documents/{artifact_id}", json={"group": "engineering-quality", "dry_run": False},
        ))

        assert Path(moved).is_relative_to(root / "docs" / "adr" / "engineering-quality")
