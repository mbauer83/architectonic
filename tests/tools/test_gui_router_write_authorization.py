"""Authorization behavior of migrated REST mutators that previously bypassed the
write pipeline: group lifecycle, viewpoint pins/create/delete, ordinary entity
writes, admin routes, and promotion — read-only and policy denials are enforced
by the executor with zero side effects, and promotion serializes behind queued
writes on the single worker.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.workspace.mutation_gate import get_workspace_gate
from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
from src.infrastructure.write.mutation_executor_registry import (
    _reset_executor_for_test,
    install_mutation_executor,
)
from src.infrastructure.write.workspace_authorization import WorkspaceAuthorizationSnapshots
from tests.support.search_visibility_fixtures import entity_md, write_file

pytest.importorskip("httpx")

ENTITY_ID = "REQ@1000000701.AthReq.authorization-probe-requirement"


def _install(engagement: Path, enterprise: Path | None, *, read_only: bool = False, admin_mode: bool = False):
    install_mutation_executor(
        build_workspace_mutation_executor(
            WorkspaceAuthorizationSnapshots(
                engagement_root=engagement,
                enterprise_root=enterprise,
                admin_mode=admin_mode,
                read_only=read_only,
                gate=get_workspace_gate(),
            )
        )
    )


@pytest.fixture()
def workspace(tmp_path: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.gui.routers.entities import router as entities_router
    from src.infrastructure.gui.routers.groups import router as groups_router
    from src.infrastructure.gui.routers.promote import router as promote_router
    from src.infrastructure.gui.routers.viewpoint_authoring import router as viewpoint_authoring_router

    engagement = tmp_path / "engagements" / "ENG-ATH" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    enterprise.mkdir(parents=True)
    write_file(
        engagement / "model" / "motivation" / "requirement" / f"{ENTITY_ID}.md",
        entity_md(ENTITY_ID, "requirement", "Authorization Probe Requirement"),
    )
    repo = ArtifactRepository(shared_artifact_index([engagement]))
    gui_state.init_state(repo, engagement, enterprise)
    _install(engagement, enterprise)
    app = FastAPI()
    from src.infrastructure.app_bootstrap import install_module_registry

    install_module_registry(app)
    for router in (entities_router, groups_router, promote_router, viewpoint_authoring_router):
        app.include_router(router)
    client = TestClient(app)
    yield client, engagement, enterprise
    _reset_executor_for_test()


class TestGroupOpsGoThroughExecutor:
    def test_create_succeeds_in_normal_mode(self, workspace) -> None:
        client, engagement, _ = workspace
        response = client.post(
            "/api/group", json={"kind": "model-project", "slug": "auth-probe", "name": "Auth Probe"}
        )
        assert response.status_code == 200, response.text

    def test_create_rejected_read_only_without_side_effects(self, workspace) -> None:
        client, engagement, enterprise = workspace
        _install(engagement, enterprise, read_only=True)
        response = client.post(
            "/api/group", json={"kind": "model-project", "slug": "denied-probe", "name": "Denied"}
        )
        assert response.status_code == 423
        assert not (engagement / "projects" / "denied-probe").exists()

    def test_delete_rejected_read_only(self, workspace) -> None:
        client, engagement, enterprise = workspace
        _install(engagement, enterprise, read_only=True)
        response = client.delete("/api/group?kind=model-project&target=anything")
        assert response.status_code == 423


class TestViewpointWritesGoThroughExecutor:
    def test_pins_put_succeeds_in_normal_mode(self, workspace) -> None:
        client, _, _ = workspace
        response = client.put("/api/viewpoints/pins", json={"slugs": []})
        assert response.status_code == 200, response.text

    def test_pins_put_rejected_read_only(self, workspace) -> None:
        client, engagement, enterprise = workspace
        _install(engagement, enterprise, read_only=True)
        response = client.put("/api/viewpoints/pins", json={"slugs": []})
        assert response.status_code == 423

    def test_delete_rejected_read_only_when_it_would_write(self, workspace) -> None:
        client, engagement, enterprise = workspace
        create = client.post(
            "/api/viewpoints",
            json={
                "definition": {"slug": "auth-probe-viewpoint", "version": 1, "name": "Auth Probe Viewpoint"},
                "dry_run": False,
            },
        )
        assert create.status_code == 200, create.text
        assert create.json()["ok"] is True
        _install(engagement, enterprise, read_only=True)
        response = client.post(
            "/api/viewpoints/remove", json={"slug": "auth-probe-viewpoint", "dry_run": False}
        )
        assert response.status_code == 423

    def test_create_rejected_read_only_when_it_would_write(self, workspace) -> None:
        client, engagement, enterprise = workspace
        _install(engagement, enterprise, read_only=True)
        response = client.post(
            "/api/viewpoints",
            json={
                "definition": {"slug": "denied-viewpoint", "version": 1, "name": "Denied Viewpoint"},
                "dry_run": False,
            },
        )
        assert response.status_code == 423


class TestOrdinaryEntityWrites:
    def test_create_rejected_read_only(self, workspace) -> None:
        client, engagement, enterprise = workspace
        _install(engagement, enterprise, read_only=True)
        response = client.post(
            "/api/entity", json={"artifact_type": "requirement", "name": "Denied Entity", "dry_run": False}
        )
        assert response.status_code == 423


@pytest.fixture()
def git_workspace(tmp_path: Path):
    """Promotion needs real git repos on both sides."""
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.gui.routers.promote import router as promote_router
    from tests.support.git_workflow_fixtures import build_workflow_pair, git

    engagement, enterprise = build_workflow_pair(tmp_path)
    write_file(
        engagement / "model" / "motivation" / "requirement" / f"{ENTITY_ID}.md",
        entity_md(ENTITY_ID, "requirement", "Authorization Probe Requirement"),
    )
    git(engagement, "add", "-A")
    git(engagement, "commit", "-m", "add probe entity")
    repo = ArtifactRepository(shared_artifact_index([engagement]))
    gui_state.init_state(repo, engagement, enterprise)
    _install(engagement, enterprise)
    app = FastAPI()
    install_module_registry(app)
    app.include_router(promote_router)
    client = TestClient(app)
    yield client, engagement, enterprise
    _reset_executor_for_test()


class TestPromotionAuthorization:
    def test_execute_rejected_read_only_without_side_effects(self, git_workspace) -> None:
        client, engagement, enterprise = git_workspace
        _install(engagement, enterprise, read_only=True)
        from tests.support.git_workflow_fixtures import git

        head_before = git(enterprise, "rev-parse", "HEAD")
        response = client.post(
            "/api/promote/execute", json={"entity_ids": [ENTITY_ID], "dry_run": False}
        )
        assert response.status_code == 423
        # No working branch, no commit, no promoted files: the enterprise repo is untouched.
        assert git(enterprise, "rev-parse", "--abbrev-ref", "HEAD") == "main"
        assert git(enterprise, "rev-parse", "HEAD") == head_before
        assert not (enterprise / "model" / "motivation" / "requirement" / f"{ENTITY_ID}.md").exists()

    def test_promotion_cannot_overlap_a_queued_write(self, git_workspace) -> None:
        """Promotion serializes on the shared single-worker queue: while another
        queued write is running, the promotion request does not execute."""
        from src.infrastructure.mcp.artifact_mcp.write_queue import submit_serialized

        client, engagement, enterprise = git_workspace
        first_started = threading.Event()
        release_first = threading.Event()
        order: list[str] = []

        def _blocker() -> None:
            order.append("queued-write-start")
            first_started.set()
            assert release_first.wait(timeout=30)
            order.append("queued-write-end")

        blocker_future = submit_serialized("blocking_write", _blocker)
        assert first_started.wait(timeout=30)

        result: dict[str, object] = {}

        def _promote() -> None:
            response = client.post(
                "/api/promote/execute", json={"entity_ids": [ENTITY_ID], "dry_run": False}
            )
            order.append("promotion-returned")
            result["status"] = response.status_code

        promote_thread = threading.Thread(target=_promote)
        promote_thread.start()
        promote_thread.join(timeout=1.0)
        assert promote_thread.is_alive(), "promotion must wait behind the queued write"
        release_first.set()
        promote_thread.join(timeout=60)
        assert not promote_thread.is_alive()
        blocker_future.result(timeout=10)
        assert order.index("queued-write-end") < order.index("promotion-returned")
        assert result["status"] == 200
