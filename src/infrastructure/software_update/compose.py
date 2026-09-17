"""The compose-host deployment: the checkout builds an image, the container serves the volumes.

Every access to the deployment's data goes through a container — the volumes' paths and uid mapping
are Docker's — so the data upgrade, its rehearsal and its restore all run `arch-repair` inside the
*new* image with `docker compose run`. The old container is stopped before the migration because the
backend-not-serving guard probes localhost and a `run` container has its own network namespace: with
the app still up, the guard would report clear while two writers held one store.

Images are anchored by version: before the compose tag is rebuilt for the new checkout, the image it
names is tagged `architectonic:<installed version>`, so a rollback that returns the checkout to that
version finds its image by name and retags it instead of rebuilding.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from src.application.software_update.installation import (
    BackendObservation,
    CheckoutMove,
    DependencySelection,
    GuiProvisioning,
)
from src.application.software_update.journal import TargetRelease
from src.application.software_update.ports import MigrationResult
from src.infrastructure.software_update import uv_environment
from src.infrastructure.software_update._commands import run_command
from src.infrastructure.software_update._migration import migration_result
from src.infrastructure.software_update.checkout import GitCheckout

#: The arguments the container entrypoint gives `arch-repair upgrade`: its settings document and the
#: workspace the mounted declaration sits in. The same identity, so the same operational targets.
CONTAINER_UPGRADE_ARGUMENTS = ("--settings", "/app/config/settings.yaml", "--workspace", "/app")
IMAGE_REPOSITORY = "architectonic"
APP_SERVICE = "app"
CONTAINER_PORT = 8000

_COMPOSE_TIMEOUT = 600
_BUILD_TIMEOUT = 3600
_MIGRATION_TIMEOUT = 3600
_START_TIMEOUT_SECONDS = 180

Runner = Callable[[list[str], int], subprocess.CompletedProcess[str]]


class ComposeError(RuntimeError):
    pass


class ComposeProject:
    """`docker compose` for this checkout's project, through one runner a test can replace."""

    def __init__(
        self, root: Path, *, compose_file: Path | None = None, runner: Runner | None = None, docker: str = "docker",
    ) -> None:
        self.root = root
        self.compose_file = compose_file
        self.docker = docker
        self._runner = runner or self._run

    def compose(self, *args: str, timeout: int = _COMPOSE_TIMEOUT) -> subprocess.CompletedProcess[str]:
        file = ["-f", str(self.compose_file)] if self.compose_file else []
        return self._runner([self.docker, "compose", *file, *args], timeout)

    def checked(self, *args: str, timeout: int = _COMPOSE_TIMEOUT) -> str:
        result = self.compose(*args, timeout=timeout)
        if result.returncode != 0:
            raise ComposeError(
                f"docker compose {' '.join(args[:2])} failed ({result.returncode}): {result.stderr[-2000:]}"
            )
        return result.stdout

    def running_app_image(self) -> str | None:
        """The image the running `app` service uses, or None when it is not running (or docker is not here)."""
        result = self.compose("ps", "--format", "json")
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("Service") == APP_SERVICE and row.get("State") == "running":
                return str(row.get("Image") or "")
        return None

    def configured_image(self) -> str:
        images = [line.strip() for line in self.checked("config", "--images").splitlines() if line.strip()]
        for image in images:
            if image.startswith(f"{IMAGE_REPOSITORY}:"):
                return image
        raise ComposeError(f"no {IMAGE_REPOSITORY} image in the compose project's services: {images}")

    def published_port(self) -> int:
        binding = self.checked("port", APP_SERVICE, str(CONTAINER_PORT)).strip()
        try:
            return int(binding.rsplit(":", 1)[1])
        except (IndexError, ValueError) as exc:
            raise ComposeError(f"cannot read the published port from {binding!r}") from exc

    def image_exists(self, image: str) -> bool:
        return self._runner([self.docker, "image", "inspect", image], _COMPOSE_TIMEOUT).returncode == 0

    def tag(self, source: str, target: str) -> None:
        result = self._runner([self.docker, "tag", source, target], _COMPOSE_TIMEOUT)
        if result.returncode != 0:
            raise ComposeError(f"docker tag {source} {target}: {result.stderr[-500:]}")

    def build(self) -> None:
        self.checked("build", APP_SERVICE, timeout=_BUILD_TIMEOUT)

    def stop(self) -> None:
        self.checked("stop", APP_SERVICE)

    def up(self) -> None:
        self.checked("up", "-d", APP_SERVICE)

    def run_tool(
        self, tool: str, *arguments: str, timeout: int = _MIGRATION_TIMEOUT,
    ) -> subprocess.CompletedProcess[str]:
        return self.compose(
            "run", "--rm", "--no-deps", "--entrypoint", tool, APP_SERVICE, *arguments, timeout=timeout,
        )

    def _run(self, command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        # In the checkout: a compose file named without `-f` is found relative to the working directory.
        return run_command(command, cwd=self.root, timeout=timeout, doing=" ".join(command[:3]))


class ComposeActions:
    """`UpdateActions` for a checkout whose deployment is the compose project beside it."""

    def __init__(
        self,
        root: Path,
        project: ComposeProject,
        *,
        installed_version: str | None,
        resolve_selection: Sequence[str] = (),
        uv: str = "uv",
        served_version: Callable[[int], str | None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.root = root
        self.project = project
        self.installed_version = installed_version
        self.resolve_selection = tuple(resolve_selection)
        self.uv = uv
        self._served_version = served_version or _served_version
        self._sleep = sleep

    # The container is stopped in `migrate`, right before the guard-blind step, so the image build
    # stays outside the downtime; the journal's phase still records that a stop belongs to the update.
    def stop_backend(self, port: int | None) -> None:
        return None

    def start_backend(self, previous: BackendObservation) -> None:
        self.project.up()
        port = self.project.published_port()
        deadline = time.monotonic() + _START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._served_version(port) is not None:
                return
            self._sleep(2.0)
        raise ComposeError(f"the app container did not answer on port {port} within {_START_TIMEOUT_SECONDS}s")

    def move_checkout(self, tag: str, move: CheckoutMove) -> None:
        GitCheckout(self.root).move_to(tag, move)

    def restore_checkout(self, commit: str, branch: str | None) -> None:
        GitCheckout(self.root).restore(commit, branch)

    def sync_environment(self, selection: DependencySelection) -> None:
        """The host environment for `arch-update` itself, and the image for the checkout as it stands."""
        uv_environment.sync(self.root, selection, uv=self.uv)
        compose_image = self.project.configured_image()
        anchor = f"{IMAGE_REPOSITORY}:{self.installed_version}" if self.installed_version else None
        declared = GitCheckout(self.root).observe().version
        if anchor is not None and str(declared) == self.installed_version and self.project.image_exists(anchor):
            self.project.tag(anchor, compose_image)  # a rollback: the installed version's image, by name
            return
        if anchor is not None and self.project.image_exists(compose_image):
            self.project.tag(compose_image, anchor)  # keep the installed version's image for a rollback
        self.project.build()

    def install_gui(self, gui: GuiProvisioning, target: TargetRelease) -> None:
        return None  # the image carries the GUI it was built with

    def restore_gui(self) -> None:
        return None

    def reconcile_assets(self) -> tuple[str, ...]:
        return ()  # the image carries its pinned assets

    def migrate(self) -> MigrationResult:
        self.project.stop()
        extra = [arg for slug in self.resolve_selection for arg in ("--resolve-selection", slug)]
        result = self.project.run_tool(
            "arch-repair", "upgrade", "--commit", "--json", *CONTAINER_UPGRADE_ARGUMENTS, *extra,
        )
        return migration_result(result, doing="arch-repair upgrade --commit (in the image)")

    def restore_checkpoint(self, checkpoint_set: str) -> None:
        self.project.stop()
        result = self.project.run_tool(
            "arch-repair", "upgrade", "--restore", checkpoint_set, *CONTAINER_UPGRADE_ARGUMENTS,
        )
        if result.returncode != 0:
            raise ComposeError(f"arch-repair upgrade --restore {checkpoint_set} failed: {result.stderr[-2000:]}")

    def authorize_store(self) -> None:
        return None  # the container's activation policy and `.env` decide; nothing is prompted

    def verify(self, target: TargetRelease, *, backend_expected: bool) -> None:
        observed = GitCheckout(self.root).observe()
        if str(observed.version) != target.version:
            raise ComposeError(f"the checkout declares {observed.version}, not {target.version}")
        served = self._served_version(self.project.published_port())
        if served != target.version:
            raise ComposeError(f"the app container serves {served or 'nothing'}, not {target.version}")


def _served_version(port: int) -> str | None:
    from src.infrastructure.backend.backend_probe import probe_identity_on_port  # noqa: PLC0415

    identity = probe_identity_on_port(port, timeout_s=3.0)
    return None if identity is None else identity.software_version
