"""A backend started detached carries the credentials its workspace's remotes need.

`arch-backend --daemon` always collected and verified them before spawning; `ensure_backend_running`
— which `arch-switch-engagement` restarts through — did not, so a workspace whose remote needs an SSH
passphrase got a child that could only prompt into `/dev/null`. One spawn now serves both, and the
credentials travel in the child's environment the way the child already reads them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.backend import backend_launch
from src.infrastructure.git.git_auth import GitCredentials


@pytest.fixture()
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    class _Proc:
        pid = 4321

    def fake_popen(command, **kwargs):  # noqa: ANN001, ANN202
        calls.append({"command": command, **kwargs})
        return _Proc()

    monkeypatch.setattr(backend_launch.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(backend_launch, "_await_own_backend", lambda port, *, workspace, log_path: port)
    command_for = lambda *, port, project_dir=None: ["arch-backend", "--port", str(port)]  # noqa: E731
    monkeypatch.setattr(backend_launch, "backend_start_command", command_for)
    return calls


def test_the_restart_path_collects_and_hands_over_the_credentials(monkeypatch, spawned, tmp_path: Path) -> None:  # noqa: ANN001
    monkeypatch.delenv("ARCH_GIT_HTTPS_TOKEN_FILE", raising=False)
    asked: list[Path] = []

    def collect(workspace: Path) -> GitCredentials:
        asked.append(workspace)
        return GitCredentials(ssh_passphrase="open sesame")

    monkeypatch.setattr(backend_launch, "workspace_git_credentials", collect)

    assert backend_launch._start_backend(8123, workspace=tmp_path, project_dir=None) == 8123

    assert asked == [tmp_path]
    env = spawned[0]["env"]
    assert isinstance(env, dict)
    assert env["ARCH_GIT_SSH_PASSWORD"] == "open sesame"
    assert spawned[0]["stdin"] is backend_launch.subprocess.DEVNULL
    assert spawned[0]["start_new_session"] is True


def test_credentials_already_collected_are_not_asked_for_again(monkeypatch, spawned, tmp_path: Path) -> None:  # noqa: ANN001
    monkeypatch.delenv("ARCH_GIT_HTTPS_TOKEN_FILE", raising=False)
    monkeypatch.setattr(backend_launch, "workspace_git_credentials", lambda workspace: pytest.fail("asked twice"))

    given = GitCredentials(https_username="u", https_password="p")
    backend_launch.start_detached(8123, workspace=tmp_path, flags=("--read-only",), credentials=given)

    command = spawned[0]["command"]
    assert command == ["arch-backend", "--port", "8123", "--read-only"]
    env = spawned[0]["env"]
    assert isinstance(env, dict)
    assert env["ARCH_GIT_HTTPS_USERNAME"] == "u"


def test_no_credentials_means_the_plain_environment(monkeypatch, spawned, tmp_path: Path) -> None:  # noqa: ANN001
    monkeypatch.setattr(backend_launch, "workspace_git_credentials", lambda workspace: None)
    monkeypatch.delenv("ARCH_GIT_SSH_PASSWORD", raising=False)

    backend_launch._start_backend(8123, workspace=tmp_path, project_dir=None)

    env = spawned[0]["env"]
    assert isinstance(env, dict)
    assert "ARCH_GIT_SSH_PASSWORD" not in env
