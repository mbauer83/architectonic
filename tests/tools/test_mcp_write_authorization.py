"""Authorization behavior of registered MCP mutation tools.

Standard authoring tools reject enterprise, enterprise-child, symlinked, and
non-configured write roots in every mode — with the enterprise rejections naming
the admin surface — and a representative formerly queued tool completes through
the executor with exactly one queue submission and one gate acquisition.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.application.mutation_authorization import MutationRejected
from src.infrastructure.mcp import mcp_artifact_server as srv
from src.infrastructure.mcp.artifact_mcp import mutation_registration
from src.infrastructure.mcp.artifact_mcp.write_queue import submit_serialized
from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate
from src.infrastructure.write.authorized_mutation_executor import AuthorizedMutationExecutor
from src.infrastructure.write.workspace_authorization import WorkspaceAuthorizationSnapshots

_TIMEOUT_S = 30.0


class _CountingGate(WorkspaceMutationGate):
    def __init__(self) -> None:
        super().__init__()
        self.acquisitions = 0

    def writing(self):
        self.acquisitions += 1
        return super().writing()


class _Workspace:
    def __init__(self, tmp_path: Path, *, admin_mode: bool = False, read_only: bool = False) -> None:
        self.engagement = tmp_path / "engagements" / "ENG-AUTH" / "architecture-repository"
        self.enterprise = tmp_path / "enterprise-repository"
        self.engagement.mkdir(parents=True)
        self.enterprise.mkdir(parents=True)
        self.gate = _CountingGate()
        self.submissions: list[str] = []

        def _counting_submitter(operation_name: str, operation):
            self.submissions.append(operation_name)
            return submit_serialized(operation_name, operation)

        mutation_registration.install_mutation_executor(
            AuthorizedMutationExecutor(
                WorkspaceAuthorizationSnapshots(
                    engagement_root=self.engagement,
                    enterprise_root=self.enterprise,
                    admin_mode=admin_mode,
                    read_only=read_only,
                    gate=self.gate,
                ),
                submitter=_counting_submitter,
                gate=self.gate,
            )
        )


@pytest.fixture(autouse=True)
def _reset_installed_executor():
    yield
    mutation_registration._reset_executor_for_test()


def _tool(name: str):
    return srv.mcp_write._tool_manager._tools[name].fn


def _call(tool_name: str, /, **kwargs: object) -> object:
    async def _invoke() -> object:
        return await asyncio.wait_for(_tool(tool_name)(**kwargs), timeout=_TIMEOUT_S)

    return asyncio.run(_invoke())


class TestStandardToolsRejectNonEngagementTargets:
    @pytest.mark.parametrize("admin_mode", [False, True])
    def test_enterprise_root_rejected_naming_admin_surface(self, tmp_path: Path, admin_mode: bool) -> None:
        ws = _Workspace(tmp_path, admin_mode=admin_mode)
        with pytest.raises(MutationRejected) as excinfo:
            _call("artifact_group", kind="model-project", action="create", target="probe",
                  name="Probe", repo_root=str(ws.enterprise))
        assert excinfo.value.denial.code == "enterprise_target_forbidden"
        assert "admin" in excinfo.value.denial.message
        assert ws.submissions == []

    @pytest.mark.parametrize("admin_mode", [False, True])
    def test_enterprise_child_rejected(self, tmp_path: Path, admin_mode: bool) -> None:
        ws = _Workspace(tmp_path, admin_mode=admin_mode)
        child = ws.enterprise / "model"
        child.mkdir()
        with pytest.raises(MutationRejected) as excinfo:
            _call("artifact_create_entity", artifact_type="requirement", name="Probe",
                  dry_run=True, repo_root=str(child))
        assert excinfo.value.denial.code == "enterprise_target_forbidden"
        assert "admin" in excinfo.value.denial.message

    def test_symlink_to_enterprise_rejected(self, tmp_path: Path) -> None:
        ws = _Workspace(tmp_path)
        link = tmp_path / "innocent-link"
        link.symlink_to(ws.enterprise)
        with pytest.raises(MutationRejected) as excinfo:
            _call("artifact_viewpoint", action="delete", slug="probe", dry_run=True,
                  repo_root=str(link))
        assert excinfo.value.denial.code == "enterprise_target_forbidden"
        assert "admin" in excinfo.value.denial.message

    def test_non_configured_root_rejected(self, tmp_path: Path) -> None:
        ws = _Workspace(tmp_path)
        stray = tmp_path / "elsewhere" / "architecture-repository"
        stray.mkdir(parents=True)
        with pytest.raises(MutationRejected) as excinfo:
            _call("artifact_bulk_write", items=[], dry_run=True, repo_root=str(stray))
        assert excinfo.value.denial.code == "target_not_engagement_root"
        assert ws.submissions == []

    def test_read_only_mode_rejects_engagement_writes(self, tmp_path: Path) -> None:
        ws = _Workspace(tmp_path, read_only=True)
        with pytest.raises(MutationRejected) as excinfo:
            _call("artifact_group", kind="model-project", action="create", target="probe",
                  name="Probe", repo_root=str(ws.engagement))
        assert excinfo.value.denial.code == "read_only"
        assert ws.submissions == []


class TestFormerlyQueuedToolsRunThroughExecutor:
    def test_group_dry_run_single_submission_single_gate(self, tmp_path: Path) -> None:
        """Timeout-bounded: the migrated tool completes through the executor with one
        queue submission and one gate acquisition — no nested wait, no deadlock."""
        ws = _Workspace(tmp_path)
        result = _call("artifact_group", kind="model-project", action="create", target="probe",
                       name="Probe", dry_run=True, repo_root=str(ws.engagement))
        assert isinstance(result, dict)
        assert ws.submissions == ["artifact_group"]
        assert ws.gate.acquisitions == 1

    def test_create_entity_dry_run_single_submission_single_gate(self, tmp_path: Path) -> None:
        ws = _Workspace(tmp_path)
        result = _call("artifact_create_entity", artifact_type="requirement", name="Probe Requirement",
                       dry_run=True, repo_root=str(ws.engagement))
        assert isinstance(result, dict)
        assert result.get("dry_run") is True
        assert ws.submissions == ["artifact_create_entity"]
        assert ws.gate.acquisitions == 1
