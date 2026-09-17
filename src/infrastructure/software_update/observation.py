"""Observing the installation `arch-update` runs in, through the modules that own each fact.

Every question here has an owner elsewhere and is asked there: the backend through `backend_control`
and `backend_process`, the store through the assurance status and credential modules, the checkout
through `GitCheckout`. This module only gathers the answers into the planner's vocabulary.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import get_args

from src.application.software_update.installation import (
    BackendObservation,
    DeploymentKind,
    InstallationObservation,
    InstalledSoftware,
    StoreObservation,
    StorePolicy,
    Tooling,
)
from src.infrastructure.software_update.uv_environment import derive_selection

#: How a serving backend's output is told apart from a terminal's: a detached backend writes to the
#: log or to nowhere, a foreground one to a pseudo-terminal.
_TERMINAL_PREFIXES = ("/dev/pts/", "/dev/tty")


def observe_installation(
    root: Path,
    software: InstalledSoftware,
    *,
    probe_remotes: bool = True,
    interactive: bool | None = None,
    compose_file: Path | None = None,
    deployment: str | None = None,
) -> InstallationObservation:
    backend = observe_backend(root)
    compose = observe_compose(root, compose_file)
    kind = deployment_kind(root, local_backend=backend.running, compose_app=compose is not None, forced=deployment)
    if kind == "compose-host" and compose is not None:
        # The deployment is the container: what serves is the published port, and the store lives in
        # a volume the host cannot see, so neither the host backend nor the host store is the subject.
        backend = BackendObservation(running=True, pid=None, port=compose, detached=True, flags=())
        store: StoreObservation = StoreObservation(configured=False, held_open=False, policy=None, key_readable=None)
    else:
        store = observe_store(root)
    return InstallationObservation(
        kind=kind,
        software=software,
        selection=derive_selection(root / "pyproject.toml"),
        backend=backend,
        store=store,
        remotes_needing_credentials=remotes_needing_credentials(root) if probe_remotes and backend.running else (),
        tooling=Tooling(uv=_on_path("uv"), npm=_on_path("npm"), gh=_on_path("gh"), docker=_on_path("docker")),
        interactive=sys.stdin.isatty() if interactive is None else interactive,
    )


def deployment_kind(
    root: Path, *, local_backend: bool = False, compose_app: bool = False, forced: str | None = None,
) -> DeploymentKind:
    """Observed, never configured — except that an operator may say which of two deployments is meant.

    A checkout with a `.git` is local; an image without one is a container; a checkout whose compose
    project runs an `app` container is a compose host; one that both serves a local backend and runs
    the container is ambiguous, and the planner refuses to guess.
    """
    from src.infrastructure.backend.backend_probe import configured_backend_url  # noqa: PLC0415

    if Path("/.dockerenv").exists() or not (root / ".git").exists():
        return "container"
    if configured_backend_url():
        return "remote-attached"
    if forced == "compose":
        return "compose-host"
    if forced == "local":
        return "local-checkout"
    if compose_app and local_backend:
        return "ambiguous"
    return "compose-host" if compose_app else "local-checkout"


def observe_compose(root: Path, compose_file: Path | None) -> int | None:
    """The published port of this checkout's running `app` container, or None when none runs."""
    from src.infrastructure.software_update.compose import ComposeError, ComposeProject  # noqa: PLC0415

    if not _on_path("docker"):
        return None
    project = ComposeProject(root, compose_file=compose_file)
    if project.running_app_image() is None:
        return None
    try:
        return project.published_port()
    except ComposeError:
        return None  # a running container with no published port is not one the update can verify


def observe_backend(root: Path) -> BackendObservation:
    from src.infrastructure.backend import backend_control  # noqa: PLC0415
    from src.infrastructure.backend.backend_process import find_arch_backend_instances  # noqa: PLC0415

    status = backend_control.backend_status(cwd=root)
    pid = status.get("pid")
    port = status.get("port")
    running = bool(status.get("running"))
    stdout = status.get("stdout")
    detached: bool | None = None
    if running and isinstance(stdout, str):
        detached = not stdout.startswith(_TERMINAL_PREFIXES)
    flags: tuple[str, ...] = ()
    if running and isinstance(pid, int):
        instance = next((item for item in find_arch_backend_instances() if item["pid"] == pid), None)
        flags = tuple(instance.get("serving_flags", [])) if instance else ()
    return BackendObservation(
        running=running,
        pid=pid if isinstance(pid, int) else None,
        port=port if isinstance(port, int) else None,
        detached=detached,
        flags=flags,
        unhealthy=status.get("reason") in {"stopped_backend", "unhealthy_backend", "unhealthy"},
    )


def observe_store(root: Path) -> StoreObservation:
    from src.config.storage_settings import (  # noqa: PLC0415
        storage_assurance_activation_policy,
        storage_assurance_store_backend,
    )
    from src.infrastructure.assurance import _credential_accounts as accounts  # noqa: PLC0415
    from src.infrastructure.cli._assurance_status import backend_holds_store_open  # noqa: PLC0415
    from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415

    manifest = resolve_manifest()
    db_path = manifest.assurance_db_path.path
    configured = manifest.assurance_enabled and storage_assurance_store_backend() == "sqlcipher" and db_path.exists()
    if not configured:
        return StoreObservation(configured=False, held_open=False, policy=None, key_readable=None)
    try:
        declared = storage_assurance_activation_policy()
    except ValueError:
        declared = ""
    policies: tuple[StorePolicy, ...] = get_args(StorePolicy)
    policy = next((known for known in policies if known == declared), None)
    held_open = backend_holds_store_open() is True
    key_readable: bool | None
    missing_env: str | None = None
    try:
        key_readable = accounts.present(accounts.DB_KEY, db_path)
    except RuntimeError:
        # No credential backend can be reached: on a headless host the vault needs its master
        # password from the environment, and that is what the restart will have to be given.
        key_readable = False
        missing_env = "ARCH_ASSURANCE_MASTER_PASSWORD"
    return StoreObservation(configured, held_open, policy, key_readable, missing_env)


def deployment_identity_arguments(root: Path) -> tuple[str, ...]:
    """The `arch-repair upgrade` arguments that name this deployment — its workspace and the settings
    document the backend runs with — so the rehearsal and the migration inspect the same operational
    targets the live process has. Without `--settings`, that command sees repositories only."""
    from src.infrastructure.deployment.layout import resolve_manifest  # noqa: PLC0415

    manifest = resolve_manifest()
    return ("--workspace", str(root), "--settings", str(manifest.settings_document.path))


def remotes_needing_credentials(
    root: Path, *, probe: Callable[[Path], bool] | None = None
) -> tuple[str, ...]:
    """The configured repositories whose remote needs a credential no environment variable supplies."""
    from src.infrastructure.git.git_auth import has_env_credentials, probe_needs_credential  # noqa: PLC0415
    from src.infrastructure.workspace.git_repos import configured_git_repos  # noqa: PLC0415

    if has_env_credentials():
        return ()
    needs = probe or probe_needs_credential
    # A configured repository that is not on disk has no remote to probe; whether the backend can
    # start without it is the backend's question, asked when it starts.
    return tuple(str(repo.path.name) for repo in configured_git_repos(root) if repo.path.is_dir() and needs(repo.path))


def _on_path(tool: str) -> bool:
    return shutil.which(tool) is not None
