"""The compose driver's order of operations, over a recorded `docker compose`, and its image anchor."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from src.application.software_update.installation import BackendObservation, DependencySelection, InstalledSoftware
from src.application.software_update.journal import TargetRelease
from src.application.software_update.ports import MigrationIncomplete
from src.application.software_update.version import ReleaseVersion
from src.infrastructure.software_update import compose
from src.infrastructure.software_update._migration import MigrationRefused
from src.infrastructure.software_update.compose import ComposeActions, ComposeError, ComposeProject

PS_RUNNING = '{"Service":"caddy","State":"running","Image":"caddy:2-alpine"}\n' \
             '{"Service":"app","State":"running","Image":"architectonic:local"}\n'


@dataclass
class FakeDocker:
    images: set[str] = field(default_factory=lambda: {"architectonic:local"})
    app_running: bool = True
    migrate_exit: int = 0
    migrate_stdout: str = '{"checkpoint_set": {"id": "20261002T090100Z"}, "outcome": "success"}'
    calls: list[str] = field(default_factory=list)

    def __call__(self, command: list[str], timeout: int) -> CompletedProcess[str]:
        words = " ".join(command)
        self.calls.append(words)
        verb = command[2] if command[1] == "compose" and command[2] != "-f" else (
            command[4] if command[1] == "compose" else command[1]
        )
        if verb == "ps":
            return CompletedProcess(command, 0, PS_RUNNING if self.app_running else "", "")
        if verb == "config":
            return CompletedProcess(command, 0, "architectonic:local\ncaddy:2-alpine\n", "")
        if verb == "port":
            return CompletedProcess(command, 0, "0.0.0.0:8000\n", "")
        if verb == "image":
            return CompletedProcess(command, 0 if command[-1] in self.images else 1, "", "")
        if verb == "tag":
            self.images.add(command[3])
            return CompletedProcess(command, 0, "", "")
        if verb == "build":
            self.images.add("architectonic:local")
            return CompletedProcess(command, 0, "", "")
        if verb == "stop":
            self.app_running = False
            return CompletedProcess(command, 0, "", "")
        if verb == "up":
            self.app_running = True
            return CompletedProcess(command, 0, "", "")
        if verb == "run" and "--commit" in command:
            return CompletedProcess(command, self.migrate_exit, self.migrate_stdout, "stderr text")
        if verb == "run" and "--restore" in command:
            return CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected docker command: {words}")


class CheckoutStub:
    def __init__(self, version: str) -> None:
        self.version = version

    def observe(self) -> InstalledSoftware:
        major, minor, patch = (int(part) for part in self.version.split("."))
        return InstalledSoftware(ReleaseVersion(major, minor, patch), "c", "main", (), True, None, None)


@pytest.fixture()
def actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    docker = FakeDocker()
    monkeypatch.setattr(compose.uv_environment, "sync", lambda root, selection, uv: docker.calls.append("uv sync"))
    served: dict[str, str | None] = {"version": "0.10.1"}

    def make(declared: str) -> ComposeActions:
        monkeypatch.setattr(compose, "GitCheckout", lambda root: CheckoutStub(declared))
        project = ComposeProject(tmp_path, runner=docker)
        return ComposeActions(
            tmp_path, project, installed_version="0.10.0", served_version=lambda port: served["version"],
            sleep=lambda s: None,
        )

    return docker, make, served


def test_the_running_app_image_and_published_port_are_read_from_compose(tmp_path: Path) -> None:
    docker = FakeDocker()
    project = ComposeProject(tmp_path, compose_file=Path("docker-compose.demo.yml"), runner=docker)

    assert project.running_app_image() == "architectonic:local" and project.published_port() == 8000
    assert docker.calls[0].startswith("docker compose -f docker-compose.demo.yml ps")
    docker.app_running = False
    assert project.running_app_image() is None


def test_going_forward_anchors_the_installed_image_by_version_and_builds(actions) -> None:  # noqa: ANN001
    docker, make, _ = actions

    make("0.10.1").sync_environment(DependencySelection(("gui",), ()))

    assert "uv sync" in docker.calls
    assert "docker tag architectonic:local architectonic:0.10.0" in docker.calls
    assert any("compose build app" in call for call in docker.calls)


def test_rolling_back_retags_the_anchor_instead_of_rebuilding(actions) -> None:  # noqa: ANN001
    docker, make, _ = actions
    docker.images.add("architectonic:0.10.0")

    make("0.10.0").sync_environment(DependencySelection(("gui",), ()))

    assert "docker tag architectonic:0.10.0 architectonic:local" in docker.calls
    assert not any("compose build" in call for call in docker.calls)


def test_migrate_stops_the_app_before_running_the_upgrade_inside_the_image(actions) -> None:  # noqa: ANN001
    docker, make, _ = actions

    result = make("0.10.1").migrate()

    stop = next(i for i, c in enumerate(docker.calls) if "compose stop app" in c)
    run = next(i for i, c in enumerate(docker.calls) if "--entrypoint arch-repair" in c)
    assert stop < run and result.checkpoint_set == "20261002T090100Z" and result.committed
    assert (
        "run --rm --no-deps --entrypoint arch-repair app upgrade --commit --json "
        "--settings /app/config/settings.yaml --workspace /app"
    ) in docker.calls[run]


def test_a_partial_migration_carries_its_checkpoint_and_a_blocked_one_wrote_nothing(actions) -> None:  # noqa: ANN001
    docker, make, _ = actions
    docker.migrate_exit = 20
    with pytest.raises(MigrationIncomplete) as partial:
        make("0.10.1").migrate()
    assert partial.value.checkpoint_set == "20261002T090100Z"

    docker.migrate_exit = 3
    with pytest.raises(MigrationRefused, match="exited 3"):
        make("0.10.1").migrate()


def test_restore_runs_inside_the_image_with_the_app_stopped(actions) -> None:  # noqa: ANN001
    docker, make, _ = actions
    docker.calls.clear()

    make("0.10.1").restore_checkpoint("20261002T090100Z")

    assert "compose stop app" in docker.calls[0]
    assert "--entrypoint arch-repair app upgrade --restore 20261002T090100Z --settings" in docker.calls[1]


def test_start_waits_for_the_container_and_verify_compares_the_served_version(actions) -> None:  # noqa: ANN001
    docker, make, served = actions
    subject = make("0.10.1")

    subject.start_backend(BackendObservation(True, None, 8000, True, ()))
    assert any("compose up -d app" in c for c in docker.calls)
    subject.verify(TargetRelease("0.10.1", "v0.10.1", "abc", None), backend_expected=True)

    served["version"] = "0.10.0"
    with pytest.raises(ComposeError, match="serves 0.10.0"):
        subject.verify(TargetRelease("0.10.1", "v0.10.1", "abc", None), backend_expected=True)


def test_the_image_carries_gui_assets_and_credentials_so_those_phases_do_nothing(actions) -> None:  # noqa: ANN001
    docker, make, _ = actions
    subject = make("0.10.1")
    docker.calls.clear()

    subject.stop_backend(8000)
    subject.install_gui("in_image", TargetRelease("0.10.1", "v0.10.1", "abc", None))
    subject.restore_gui()
    subject.authorize_store()

    assert subject.reconcile_assets() == () and docker.calls == []
