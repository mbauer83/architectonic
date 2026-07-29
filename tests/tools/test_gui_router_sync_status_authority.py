"""Sync status carries a FRESH per-intent authority projection on every request:
live gate transitions are visible immediately through the real
``gate.blocking_writes()`` production path (no TTL), persisted health survives
reconnects, read-only keeps ahead-counts truthful, and the underlying lifecycle
rows (accumulating+clean+ahead=0, pending+dirty) are reported faithfully.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.git import enterprise_git_ops, enterprise_sync_state
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers import sync_status_cache
from src.infrastructure.gui.routers.sync import router as sync_router
from src.infrastructure.workspace.mutation_gate import get_workspace_gate
from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
from src.infrastructure.write.mutation_executor_registry import install_mutation_executor
from src.infrastructure.write.workspace_authorization import (
    WorkspaceAuthorizationSnapshots,
    persisted_sync_health,
)
from tests.support.git_workflow_fixtures import build_workflow_pair, write_entity

pytest.importorskip("httpx")


def _install(engagement: Path, enterprise: Path, *, read_only: bool = False) -> None:
    install_mutation_executor(
        build_workspace_mutation_executor(
            WorkspaceAuthorizationSnapshots(
                engagement_root=engagement,
                enterprise_root=enterprise,
                admin_mode=False,
                read_only=read_only,
                gate=get_workspace_gate(),
                sync_health=persisted_sync_health(enterprise),
            )
        )
    )


@pytest.fixture()
def workspace(tmp_path: Path):
    from starlette.testclient import TestClient

    sync_status_cache.reset_sync_status_cache()
    engagement, enterprise = build_workflow_pair(tmp_path)
    repo = ArtifactRepository(shared_artifact_index([engagement]))
    gui_state.init_state(repo, engagement, enterprise)
    _install(engagement, enterprise)
    app = FastAPI()
    app.include_router(sync_router)
    client = TestClient(app)
    yield client, engagement, enterprise
    sync_status_cache.reset_sync_status_cache()


def _authority(client) -> dict:
    response = client.get("/api/sync/status")
    assert response.status_code == 200, response.text
    return response.json()["authority"]


class TestAuthorityFreshness:
    def test_live_gate_transition_is_visible_immediately(self, workspace) -> None:
        client, _, _ = workspace
        assert _authority(client)["block_kind"] == "none"
        with get_workspace_gate().blocking_writes("sync_in_progress"):
            during = _authority(client)
            assert during["block_kind"] == "sync_in_progress"
            assert during["denied_intents"]["engagement_authoring"]["denied"] is True
            assert during["denied_intents"]["maintenance"]["denied"] is False
        after = _authority(client)
        assert after["block_kind"] == "none"
        assert after["denied_intents"]["engagement_authoring"]["denied"] is False

    def test_persisted_health_reconstructs_on_a_fresh_request(self, workspace) -> None:
        """A tab joining during a health block sees the reason and the per-intent
        denials from the snapshot alone."""
        client, _, enterprise = workspace
        enterprise_sync_state.record_block(enterprise, "fetch_failed", "origin unreachable")
        authority = _authority(client)
        assert authority["block_kind"] == "sync_health"
        assert authority["blocked_reason"] == "fetch_failed"
        denied = authority["denied_intents"]
        assert denied["enterprise_submit"]["denied"] is True
        assert denied["promotion"]["denied"] is True
        assert denied["enterprise_discard_pending"]["denied"] is True
        assert denied["enterprise_save"]["denied"] is False
        assert denied["enterprise_discard_local"]["denied"] is False
        assert denied["engagement_authoring"]["denied"] is False
        payload = client.get("/api/sync/status").json()
        assert payload["enterprise"]["health"]["reason"] == "fetch_failed"

    def test_read_only_denies_all_external_intents(self, workspace) -> None:
        client, engagement, enterprise = workspace
        _install(engagement, enterprise, read_only=True)
        authority = _authority(client)
        assert authority["block_kind"] == "read_only"
        for action, decision in authority["denied_intents"].items():
            expected = action != "maintenance"
            assert decision["denied"] is expected, action


class TestLifecycleRows:
    def test_accumulating_clean_ahead_zero(self, workspace) -> None:
        client, _, enterprise = workspace
        enterprise_git_ops.ensure_working_branch(enterprise)
        sync_status_cache.reset_sync_status_cache()
        payload = client.get("/api/sync/status").json()["enterprise"]
        assert payload["status"] == "accumulating"
        assert payload["has_uncommitted_changes"] is False
        assert payload["commits_ahead"] == 0

    def test_pending_dirty_is_reported_truthfully(self, workspace) -> None:
        client, _, enterprise = workspace
        enterprise_git_ops.ensure_working_branch(enterprise)
        write_entity(enterprise, "REQ@1000001001.StaPen.pending-probe", "Pending Probe")
        enterprise_git_ops.commit_enterprise_work(enterprise, "work")
        enterprise_git_ops.push_enterprise_branch(enterprise)
        write_entity(enterprise, "REQ@1000001002.StaDrt.dirty-probe", "Dirty Probe")
        sync_status_cache.reset_sync_status_cache()
        payload = client.get("/api/sync/status").json()["enterprise"]
        assert payload["status"] == "pending"
        assert payload["has_uncommitted_changes"] is True

    def test_read_only_mode_still_measures_ahead_counts(self, workspace) -> None:
        client, engagement, enterprise = workspace
        enterprise_git_ops.ensure_working_branch(enterprise)
        write_entity(enterprise, "REQ@1000001003.StaAhd.ahead-probe", "Ahead Probe")
        enterprise_git_ops.commit_enterprise_work(enterprise, "ahead work")
        _install(engagement, enterprise, read_only=True)
        sync_status_cache.reset_sync_status_cache()
        payload = client.get("/api/sync/status").json()["enterprise"]
        assert payload["status"] == "accumulating"
        assert payload["commits_ahead"] == 1
