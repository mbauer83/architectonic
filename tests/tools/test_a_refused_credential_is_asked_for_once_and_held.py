"""A save refused for want of a git credential is answered with a typed refusal, the credential is
supplied once through `PUT /api/sync/credentials`, and the repeated save goes through.

Driven over a real repository whose origin fetches from a local path and pushes over an ssh stand-in
that wants a passphrase (`tests/support/fake_ssh_remote.py`). Nothing reaches a network or a real key.

Also held here, because they are the conditions the route exists under:
- the route is refused to a client that is not on the loopback, and to one without the operator header;
- the secret never appears in a response body or in a log record, whether it is accepted or refused.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.git import held_credentials
from src.infrastructure.rest.contracts.operator_request import operator_request_headers
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.sync.router import router as sync_router
from src.infrastructure.workspace.mutation_gate import get_workspace_gate
from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
from src.infrastructure.write.mutation_executor_registry import (
    _reset_executor_for_test,
    install_mutation_executor,
)
from src.infrastructure.write.workspace_authorization import WorkspaceAuthorizationSnapshots
from tests.support import fake_ssh_remote
from tests.support.api_app import build_api_app
from tests.support.git_workflow_fixtures import build_workflow_pair, git, write_entity

PASSPHRASE = "correct horse battery staple"
WRONG = "tr0ub4dor-and-3"
_LOOPBACK = ("127.0.0.1", 50123)
_REMOTE = ("10.20.20.99", 50123)


@pytest.fixture
def ssh_pushing_engagement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, Path]]:
    """An engagement repository that fetches from a path and pushes over the ssh stand-in."""
    for name in ("ARCH_GIT_SSH_PASSWORD", "SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "SSH_AUTH_SOCK"):
        monkeypatch.delenv(name, raising=False)
    for name, value in fake_ssh_remote.install(tmp_path / "ssh", PASSPHRASE).items():
        monkeypatch.setenv(name, value)
    engagement, enterprise = build_workflow_pair(tmp_path)
    bare = tmp_path / "engagement-origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    git(engagement, "remote", "add", "origin", str(bare))
    git(engagement, "push", "-u", "origin", "main")
    git(engagement, "remote", "set-url", "--push", "origin", fake_ssh_remote.ssh_url(bare))

    repo = ArtifactRepository(shared_artifact_index([engagement]))
    gui_state.init_state(repo, engagement, enterprise)
    install_mutation_executor(
        build_workspace_mutation_executor(
            WorkspaceAuthorizationSnapshots(
                engagement_root=engagement, enterprise_root=enterprise, admin_mode=False,
                read_only=False, gate=get_workspace_gate(),
            )
        )
    )
    held_credentials.release()
    yield engagement, bare
    held_credentials.release()
    _reset_executor_for_test()


def _client(client: tuple[str, int] = _LOOPBACK) -> TestClient:
    return TestClient(build_api_app(sync_router), base_url="http://127.0.0.1:8188", client=client)


def _supply(client: TestClient, secret: str, *, headers: dict[str, str] | None = None) -> object:
    return client.put(
        "/api/sync/credentials",
        json={"protocol": "ssh", "secret": secret},
        headers=operator_request_headers() if headers is None else headers,
    )


def _save(client: TestClient) -> object:
    return client.post("/api/sync/engagement/save", json={"message": "save work", "push": True})


def test_a_refused_push_asks_for_the_credential_and_the_repeated_save_publishes(
    ssh_pushing_engagement: tuple[Path, Path], caplog: pytest.LogCaptureFixture,
) -> None:
    engagement, bare = ssh_pushing_engagement
    caplog.set_level(logging.DEBUG)
    write_entity(engagement, "REQ@1000000603.WfNew.newly-authored-requirement", "Newly Authored Requirement")
    client = _client()

    refused = _save(client)
    assert refused.status_code == 409, refused.text
    body = refused.json()["detail"]
    assert body["code"] == "git_credentials_required"
    assert body["details"] == {
        "protocol": "ssh", "remote": fake_ssh_remote.ssh_url(bare), "rejected": False,
    }

    wrong = _supply(client, WRONG)
    assert wrong.status_code == 409, wrong.text
    assert wrong.json()["detail"]["details"]["rejected"] is True
    assert held_credentials.held() is None, "a refused credential is not kept"

    accepted = _supply(client, PASSPHRASE)
    assert accepted.status_code == 204, accepted.text
    assert accepted.content == b""

    repeated = _save(client)
    assert repeated.status_code == 200, repeated.text
    assert git(bare, "rev-parse", "main") == git(engagement, "rev-parse", "HEAD")

    for response in (refused, wrong, accepted, repeated):
        assert PASSPHRASE not in response.text and WRONG not in response.text
    logged = "\n".join(record.getMessage() for record in caplog.records) + caplog.text
    assert PASSPHRASE not in logged and WRONG not in logged
    assert PASSPHRASE not in repr(held_credentials.held())


def test_a_submit_whose_push_url_is_ssh_is_asked_for_and_repeated(
    ssh_pushing_engagement: tuple[Path, Path], tmp_path: Path,
) -> None:
    """The reported case: the enterprise remote fetches from one URL and pushes over ssh."""
    enterprise = tmp_path / "enterprise-repository"
    bare = tmp_path / "enterprise-origin.git"
    git(enterprise, "remote", "set-url", "--push", "origin", fake_ssh_remote.ssh_url(bare))
    client = _client()
    write_entity(enterprise, "REQ@1000000608.WfSub.submit-probe", "Submit Probe")
    assert client.post("/api/sync/enterprise/save", json={"message": "pre-submit save"}).status_code == 200

    refused = client.post("/api/sync/enterprise/submit")
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["details"]["remote"] == fake_ssh_remote.ssh_url(bare)

    assert _supply(client, PASSPHRASE).status_code == 204
    submitted = client.post("/api/sync/enterprise/submit")
    assert submitted.status_code == 200, submitted.text
    assert git(bare, "branch", "--list", submitted.json()["branch"]) != ""


def test_a_request_from_another_host_is_refused(ssh_pushing_engagement: tuple[Path, Path]) -> None:
    response = _supply(_client(_REMOTE), PASSPHRASE)
    assert response.status_code == 403
    assert response.json()["detail"]["details"]["reason_code"] == "operator_request_required"
    assert PASSPHRASE not in response.text
    assert held_credentials.held() is None


def test_a_loopback_request_without_the_operator_header_is_refused(
    ssh_pushing_engagement: tuple[Path, Path],
) -> None:
    """What a page from another origin in the operator's browser could send: same machine, no header."""
    response = _supply(_client(), PASSPHRASE, headers={})
    assert response.status_code == 403
    assert held_credentials.held() is None


def test_a_malformed_body_does_not_echo_the_secret(ssh_pushing_engagement: tuple[Path, Path]) -> None:
    response = _client().put(
        "/api/sync/credentials",
        json={"protocol": "telnet", "secret": PASSPHRASE},
        headers=operator_request_headers(),
    )
    assert response.status_code == 422
    assert PASSPHRASE not in response.text


def test_each_transport_says_the_one_refusal_with_its_own_remedy(
    ssh_pushing_engagement: tuple[Path, Path],
) -> None:
    """The refusal is the git package's sentence; REST adds the GUI prompt, MCP says why it takes no secret.
    Not a `RuntimeError`, so neither the routes' nor the tools' handling of other failures swallows it."""
    from src.infrastructure.git.credential_refusal import GitCredentialsRequired  # noqa: PLC0415
    from src.infrastructure.mcp.artifact_mcp.write import sync_ops  # noqa: PLC0415

    engagement, bare = ssh_pushing_engagement
    write_entity(engagement, "REQ@1000000609.WfMcp.refused-over-both", "Refused Over Both")

    over_rest = _save(_client()).json()["detail"]["message"]
    over_mcp = sync_ops.artifact_save_changes(message="save work", push=True)

    refusal = f"The SSH key passphrase for origin ({fake_ssh_remote.ssh_url(bare)}) is needed."
    assert over_rest.startswith(refusal) and "when the GUI asks" in over_rest
    assert over_mcp["ok"] is False
    assert str(over_mcp["error"]).startswith(refusal) and "not accepted over MCP" in str(over_mcp["error"])
    assert not issubclass(GitCredentialsRequired, RuntimeError)
