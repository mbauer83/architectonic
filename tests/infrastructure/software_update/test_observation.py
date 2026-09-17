"""The deployment kind and the backend's detachment are read from what the machine shows."""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from src.infrastructure.software_update import observation
from src.infrastructure.software_update.observation import deployment_kind, observe_backend


def test_a_checkout_without_git_is_a_container_and_an_attached_url_is_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ARCH_MCP_BACKEND_URL", raising=False)
    assert deployment_kind(tmp_path) == "container"
    (tmp_path / ".git").mkdir()
    assert deployment_kind(tmp_path) == "local-checkout"
    monkeypatch.setenv("ARCH_MCP_BACKEND_URL", "http://team-host:8000")
    assert deployment_kind(tmp_path) == "remote-attached"


@pytest.mark.parametrize(
    ("status", "detached", "unhealthy"),
    [
        ({"running": True, "pid": 7, "port": 8000, "reason": "ok", "stdout": "/home/x/.arch/backend.log"}, True, False),
        ({"running": True, "pid": 7, "port": 8000, "reason": "ok", "stdout": "/dev/pts/3"}, False, False),
        ({"running": True, "pid": 7, "port": 8000, "reason": "ok", "stdout": "/dev/null"}, True, False),
        ({"running": False, "reason": "not_running"}, None, False),
        ({"running": False, "pid": 7, "port": 8000, "reason": "stopped_backend", "stdout": "/dev/pts/1"}, None, True),
    ],
    ids=["log", "terminal", "devnull", "not-running", "suspended"],
)
def test_the_backend_observation_reads_detachment_and_health_from_the_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: dict, detached: bool | None, unhealthy: bool,
) -> None:
    monkeypatch.setattr(observation, "find_arch_backend_instances", lambda: [], raising=False)
    from src.infrastructure.backend import backend_control, backend_process

    monkeypatch.setattr(backend_control, "backend_status", lambda cwd=None, port=None: status)
    monkeypatch.setattr(
        backend_process, "find_arch_backend_instances",
        lambda: [{"pid": 7, "serving_flags": ["--admin-mode"]}] if status.get("running") else [],
    )

    observed = observe_backend(tmp_path)

    assert observed.running is bool(status.get("running"))
    assert observed.detached is detached
    assert observed.unhealthy is unhealthy
    assert observed.flags == (("--admin-mode",) if status.get("running") else ())


def test_a_configured_repository_that_is_not_on_disk_is_not_probed_for_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infrastructure.workspace import git_repos

    present = tmp_path / "present"
    present.mkdir()
    specs = [
        types.SimpleNamespace(path=present), types.SimpleNamespace(path=tmp_path / "absent"),
    ]
    monkeypatch.setattr(git_repos, "configured_git_repos", lambda root: specs)
    monkeypatch.setattr("src.infrastructure.git.git_auth.has_env_credentials", lambda: False)
    probed: list[Path] = []

    def probe(path: Path) -> bool:
        probed.append(path)
        return True

    assert observation.remotes_needing_credentials(tmp_path, probe=probe) == ("present",)
    assert probed == [present]


@pytest.mark.parametrize(
    ("local_backend", "compose_app", "forced", "expected"),
    [
        (False, False, None, "local-checkout"),
        (True, False, None, "local-checkout"),
        (False, True, None, "compose-host"),
        (True, True, None, "ambiguous"),
        (True, True, "compose", "compose-host"),
        (True, True, "local", "local-checkout"),
    ],
)
def test_a_running_compose_app_makes_a_compose_host_and_two_deployments_are_ambiguous_unless_told(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local_backend: bool, compose_app: bool, forced: str | None,
    expected: str,
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.delenv("ARCH_MCP_BACKEND_URL", raising=False)

    kind = observation.deployment_kind(tmp_path, local_backend=local_backend, compose_app=compose_app, forced=forced)

    assert kind == expected
