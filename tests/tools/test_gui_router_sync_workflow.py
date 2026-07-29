"""Real-git REST tests for the save / submit / withdraw workflow routes under the
authorized mutation executor: normal-mode success, read-only and health-fault
denials with zero side effects, the save-commit verifier, and synced-dirty Save
remaining available under enterprise health warnings.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.application.mutation_authorization import SyncHealth
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.sync import router as sync_router
from src.infrastructure.workspace.mutation_gate import get_workspace_gate
from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
from src.infrastructure.write.mutation_executor_registry import (
    _reset_executor_for_test,
    install_mutation_executor,
)
from src.infrastructure.write.workspace_authorization import WorkspaceAuthorizationSnapshots
from tests.support.git_workflow_fixtures import (
    build_workflow_pair,
    git,
    write_entity,
)

pytest.importorskip("httpx")


def _install(
    engagement: Path,
    enterprise: Path,
    *,
    read_only: bool = False,
    sync_health: Callable[[], SyncHealth] | None = None,
) -> None:
    kwargs = {} if sync_health is None else {"sync_health": sync_health}
    install_mutation_executor(
        build_workspace_mutation_executor(
            WorkspaceAuthorizationSnapshots(
                engagement_root=engagement,
                enterprise_root=enterprise,
                admin_mode=False,
                read_only=read_only,
                gate=get_workspace_gate(),
                **kwargs,
            )
        )
    )


@pytest.fixture()
def workflow(tmp_path: Path):
    from starlette.testclient import TestClient

    engagement, enterprise = build_workflow_pair(tmp_path)
    repo = ArtifactRepository(shared_artifact_index([engagement]))
    gui_state.init_state(repo, engagement, enterprise)
    _install(engagement, enterprise)
    app = FastAPI()
    app.include_router(sync_router)
    client = TestClient(app)
    yield client, engagement, enterprise
    _reset_executor_for_test()


def _fetch_fault() -> SyncHealth:
    return SyncHealth(reason="fetch_failed", message="origin unreachable")


class TestEngagementSave:
    def test_valid_tree_commits(self, workflow) -> None:
        client, engagement, _ = workflow
        write_entity(engagement, "REQ@1000000603.WfNew.newly-authored-requirement", "Newly Authored Requirement")
        response = client.post("/api/sync/engagement/save", json={"message": "save work", "push": False})
        assert response.status_code == 200, response.text
        assert response.json()["ok"] is True
        assert "save work" in git(engagement, "log", "-1", "--format=%s")

    def test_malformed_artifact_rejected_with_no_commit(self, workflow) -> None:
        client, engagement, _ = workflow
        broken = engagement / "model" / "motivation" / "requirement" / "REQ@1000000604.WfBad.broken.md"
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_text("no frontmatter at all\n", encoding="utf-8")
        head_before = git(engagement, "rev-parse", "HEAD")
        response = client.post("/api/sync/engagement/save", json={"message": "bad save", "push": False})
        assert response.status_code == 400
        assert "verification" in response.json()["detail"]
        assert git(engagement, "rev-parse", "HEAD") == head_before
        assert git(engagement, "status", "--porcelain") != ""

    def test_read_only_rejected_without_side_effects(self, workflow) -> None:
        client, engagement, enterprise = workflow
        _install(engagement, enterprise, read_only=True)
        write_entity(engagement, "REQ@1000000605.WfRo.read-only-probe", "Read Only Probe")
        head_before = git(engagement, "rev-parse", "HEAD")
        response = client.post("/api/sync/engagement/save", json={"message": "denied", "push": False})
        assert response.status_code == 423
        assert git(engagement, "rev-parse", "HEAD") == head_before


class TestEnterpriseSave:
    def test_creates_working_branch_and_commit(self, workflow) -> None:
        client, _, enterprise = workflow
        write_entity(enterprise, "REQ@1000000606.WfEsv.enterprise-save-probe", "Enterprise Save Probe")
        response = client.post("/api/sync/enterprise/save", json={"message": "enterprise save"})
        assert response.status_code == 200, response.text
        branch = git(enterprise, "rev-parse", "--abbrev-ref", "HEAD")
        assert branch.startswith("arch/work-")
        assert "enterprise save" in git(enterprise, "log", "-1", "--format=%s")

    def test_dirty_save_succeeds_under_persisted_fetch_fault(self, workflow) -> None:
        """A remote-relationship health fault must not block the local commit that
        resolves a dirty enterprise tree — Save is offered AND accepted."""
        client, engagement, enterprise = workflow
        _install(engagement, enterprise, sync_health=_fetch_fault)
        write_entity(enterprise, "REQ@1000000607.WfHlt.health-save-probe", "Health Save Probe")
        response = client.post("/api/sync/enterprise/save", json={"message": "save under warning"})
        assert response.status_code == 200, response.text
        assert "save under warning" in git(enterprise, "log", "-1", "--format=%s")


class TestEnterpriseSubmit:
    def _save(self, client, enterprise: Path) -> None:
        write_entity(enterprise, "REQ@1000000608.WfSub.submit-probe", "Submit Probe")
        assert client.post("/api/sync/enterprise/save", json={"message": "pre-submit save"}).status_code == 200

    def test_submit_pushes_branch_with_upstream(self, workflow) -> None:
        client, _, enterprise = workflow
        self._save(client, enterprise)
        response = client.post("/api/sync/enterprise/submit")
        assert response.status_code == 200, response.text
        branch = response.json()["branch"]
        assert git(enterprise, "ls-remote", "--heads", "origin", branch) != ""
        assert git(enterprise, "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}") == f"origin/{branch}"

    def test_submit_denied_under_fetch_fault_with_no_push(self, workflow) -> None:
        client, engagement, enterprise = workflow
        self._save(client, enterprise)
        _install(engagement, enterprise, sync_health=_fetch_fault)
        branch = git(enterprise, "rev-parse", "--abbrev-ref", "HEAD")
        state_before = (enterprise / ".arch" / "enterprise-sync.json").read_text(encoding="utf-8")
        response = client.post("/api/sync/enterprise/submit")
        assert response.status_code == 423
        assert "fetch_failed" in response.json()["detail"]
        assert git(enterprise, "ls-remote", "--heads", "origin", branch) == ""
        assert (enterprise / ".arch" / "enterprise-sync.json").read_text(encoding="utf-8") == state_before


class TestEnterpriseWithdraw:
    def _save(self, client, enterprise: Path) -> None:
        write_entity(enterprise, "REQ@1000000609.WfWdr.withdraw-probe", "Withdraw Probe")
        assert client.post("/api/sync/enterprise/save", json={"message": "pre-withdraw save"}).status_code == 200

    def test_local_discard_returns_to_main(self, workflow) -> None:
        client, _, enterprise = workflow
        self._save(client, enterprise)
        branch = git(enterprise, "rev-parse", "--abbrev-ref", "HEAD")
        response = client.post("/api/sync/enterprise/withdraw", json={"confirm": True})
        assert response.status_code == 200, response.text
        assert git(enterprise, "rev-parse", "--abbrev-ref", "HEAD") == "main"
        assert branch not in git(enterprise, "branch", "--list", branch)

    def test_local_discard_allowed_under_fetch_fault(self, workflow) -> None:
        """Local branch discard is a local-only recovery step — remote faults must
        not deny it (only the pending-remote variant is denied)."""
        client, engagement, enterprise = workflow
        self._save(client, enterprise)
        _install(engagement, enterprise, sync_health=_fetch_fault)
        response = client.post("/api/sync/enterprise/withdraw", json={"confirm": True})
        assert response.status_code == 200, response.text
        assert git(enterprise, "rev-parse", "--abbrev-ref", "HEAD") == "main"

    def test_read_only_rejected_with_state_preserved(self, workflow) -> None:
        client, engagement, enterprise = workflow
        self._save(client, enterprise)
        _install(engagement, enterprise, read_only=True)
        branch = git(enterprise, "rev-parse", "--abbrev-ref", "HEAD")
        response = client.post("/api/sync/enterprise/withdraw", json={"confirm": True})
        assert response.status_code == 423
        assert git(enterprise, "rev-parse", "--abbrev-ref", "HEAD") == branch
