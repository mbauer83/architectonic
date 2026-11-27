"""A saved commit is authored by the identity the server is configured with, never by the request.

Regression: `POST /api/sync/engagement/save` and `/api/sync/enterprise/save` took `author_name` and
`author_email` from the request body, and the MCP tool `artifact_save_changes` took them as arguments,
so any client could record a commit under any person's name. Authorship is a fact the server
establishes; until there is a principal to take it from, it is the configured service identity.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp.artifact_mcp.write.sync_ops import artifact_save_changes
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.sync.router import router as sync_router
from src.infrastructure.workspace.mutation_gate import get_workspace_gate
from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
from src.infrastructure.write.mutation_executor_registry import (
    _reset_executor_for_test,
    install_mutation_executor,
)
from src.infrastructure.write.workspace_authorization import WorkspaceAuthorizationSnapshots
from tests.support.api_app import build_api_app
from tests.support.git_workflow_fixtures import build_workflow_pair, git, write_entity

pytest.importorskip("httpx")

_SERVICE = ("Configured Service", "service@example.invalid")
_ASSERTED = {"author_name": "Someone Else", "author_email": "someone@example.invalid"}


@pytest.fixture()
def workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from starlette.testclient import TestClient

    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ARCH_GIT_AUTHOR_NAME", _SERVICE[0])
    monkeypatch.setenv("ARCH_GIT_AUTHOR_EMAIL", _SERVICE[1])
    engagement, enterprise = build_workflow_pair(tmp_path)
    gui_state.init_state(ArtifactRepository(shared_artifact_index([engagement])), engagement, enterprise)
    install_mutation_executor(
        build_workspace_mutation_executor(
            WorkspaceAuthorizationSnapshots(
                engagement_root=engagement,
                enterprise_root=enterprise,
                admin_mode=False,
                read_only=False,
                gate=get_workspace_gate(),
            )
        )
    )
    yield TestClient(build_api_app(sync_router)), engagement, enterprise
    _reset_executor_for_test()


def _author(repo: Path) -> tuple[str, str]:
    name, email = git(repo, "log", "-1", "--format=%an|%ae").split("|")
    return name, email


@pytest.mark.parametrize("route", ["/api/sync/engagement/save", "/api/sync/enterprise/save"])
def test_a_save_naming_an_author_is_refused_and_commits_nothing(workflow, route: str) -> None:
    client, engagement, enterprise = workflow
    repo = engagement if "engagement" in route else enterprise
    write_entity(repo, "REQ@1000000611.AuRq.asserted-author-probe", "Asserted Author Probe")
    head_before = git(repo, "rev-parse", "HEAD")

    response = client.post(route, json={"message": "save", "push": False, **_ASSERTED})

    assert response.status_code == 422, response.text
    assert git(repo, "rev-parse", "HEAD") == head_before


@pytest.mark.parametrize("route", ["/api/sync/engagement/save", "/api/sync/enterprise/save"])
def test_a_save_is_authored_and_committed_by_the_configured_identity(workflow, route: str) -> None:
    client, engagement, enterprise = workflow
    repo = engagement if "engagement" in route else enterprise
    write_entity(repo, "REQ@1000000612.AuSv.server-author-probe", "Server Author Probe")

    response = client.post(route, json={"message": "save", "push": False})

    assert response.status_code == 200, response.text
    assert _author(repo) == _SERVICE
    assert tuple(git(repo, "log", "-1", "--format=%cn|%ce").split("|")) == _SERVICE


def test_the_mcp_save_tool_takes_no_author() -> None:
    parameters = inspect.signature(artifact_save_changes).parameters
    assert not {"author_name", "author_email"} & set(parameters)


def test_the_mcp_save_is_authored_by_the_configured_identity(workflow) -> None:
    _, engagement, _ = workflow
    write_entity(engagement, "REQ@1000000613.AuMc.mcp-author-probe", "MCP Author Probe")

    result = artifact_save_changes(message="save", target="engagement", push=False)

    assert result["ok"] is True, result
    assert _author(engagement) == _SERVICE
