"""Getting a backend that serves *this* workspace, starting one only if none does.

Separate from `backend_control` (which inspects and stops) because the question here is different:
not "what is running" but "which endpoint may this workspace use". The answer is a plan, made in
`domain.deployment.backend_endpoint`; this module executes it.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from src.domain.deployment.backend_endpoint import (
    AttachToBackend,
    EndpointState,
    RefuseEndpoint,
    StartBackendOn,
    WorkspaceClaim,
)
from src.infrastructure.backend.backend_endpoint import (
    plan_workspace_endpoint,
    port_serves_workspace,
    workspace_claim,
)
from src.infrastructure.backend.backend_probe import (
    backend_start_command,
    configured_backend_url,
    probe_backend,
    probe_backend_identity,
    probe_backend_url,
    resolve_backend_port,
)
from src.infrastructure.backend.backend_state import backend_log_path, read_backend_state
from src.infrastructure.git.git_auth import (
    GitCredentials,
    collect_verified_credentials,
    credentials_to_env_overrides,
)
from src.infrastructure.workspace.git_repos import configured_git_repos

logger = logging.getLogger(__name__)

#: How long a freshly spawned backend has to answer before the caller is told it did not.
STARTUP_DEADLINE_SECONDS = 15.0
_STARTUP_POLL_SECONDS = 0.25


def ensure_backend_running(
    *,
    port: int | None = None,
    start_if_missing: bool = True,
    cwd: Path | None = None,
    project_dir: Path | None = None,
) -> int:
    """The port of a backend serving this workspace, starting one when allowed.

    Never returns a port served by another workspace: that is exactly the failure this exists to
    prevent, and it is silent when it happens — both backends answer every request correctly, just
    about the wrong model.
    """
    workspace = cwd or Path.cwd()
    external_url = configured_backend_url()
    if external_url:
        return _attach_external(external_url, workspace=workspace, explicit_port=port)

    plan = plan_workspace_endpoint(cwd=workspace, explicit_port=port, may_start=start_if_missing)
    match plan:
        case AttachToBackend(port=live):
            logger.info("Reusing the backend serving this workspace on port %s", live)
            return live
        case StartBackendOn(port=chosen, moved_from=moved, moved_because=because):
            _announce_relocation(chosen, moved, because)
            return _start_backend(chosen, workspace=workspace, project_dir=project_dir)
        case RefuseEndpoint(reason=reason):
            raise RuntimeError(reason)


def _attach_external(external_url: str, *, workspace: Path, explicit_port: int | None) -> int:
    """Use the backend an operator named, and say what it turns out to be serving.

    Not identity-gated: a container publishes the roots it sees inside itself, which never match a
    host workspace's paths, so gating here would refuse every legitimate remote deployment. Naming a
    URL is a decision; the log records what that decision reached.
    """
    if not probe_backend_url(external_url):
        raise RuntimeError(f"Configured external backend is not reachable: {external_url}")
    identity = probe_backend_identity(external_url)
    logger.info(
        "Using externally configured backend at %s (serving %s)",
        external_url,
        ", ".join(identity.repo_roots) if identity is not None else "repositories it does not report",
    )
    return resolve_backend_port(start=workspace, explicit_port=explicit_port)


def _announce_relocation(chosen: int, moved_from: int | None, because: EndpointState | None) -> None:
    if moved_from is None:
        return
    logger.warning(
        "Port %s is not available for this workspace (%s); starting its backend on port %s instead. "
        "Set backend.port in arch-workspace.yaml to fix this workspace's address.",
        moved_from,
        because,
        chosen,
    )


def workspace_git_credentials(workspace: Path) -> GitCredentials | None:
    """The credentials this workspace's remotes need, collected and verified — or None if none do.

    The same prompt-and-verify loop `arch-backend --daemon` has always run before spawning: a wrong
    passphrase typed at a TTY is re-asked, a wrong one from the environment fails loudly, and a
    workspace with no remote needing any is asked nothing. A detached start that skipped this handed
    the child a prompt it could only answer into `/dev/null`.
    """
    return collect_verified_credentials([repo.path for repo in configured_git_repos(workspace)])


def spawn_detached(
    command: list[str], *, workspace: Path, log_path: Path, credentials: GitCredentials | None
) -> int:
    """Start `command` as a detached session writing to `log_path`, carrying `credentials`.

    The one place a backend is spawned: stdin from nowhere, output into the workspace's log, its own
    session so a closing terminal cannot take it down, and the credentials handed over in the
    environment the way the child already reads them. Returns the pid.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **credentials_to_env_overrides(credentials)}
    logger.info("Starting backend with command: %s", " ".join(command))
    with open(log_path, "ab") as log:
        process = subprocess.Popen(
            command,
            cwd=str(workspace),
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    return int(process.pid)


def start_detached(
    port: int,
    *,
    workspace: Path,
    project_dir: Path | None = None,
    flags: tuple[str, ...] = (),
    credentials: GitCredentials | None = None,
) -> int:
    """Start this workspace's backend detached on `port` and wait until it serves the workspace.

    `flags` are the serving flags a restart carries over (`--admin-mode`, `--read-only`,
    `--host <address>`); `credentials` are ones a caller has already collected — the updater asks for
    them before it stops anything — and are collected here when not given.
    """
    if credentials is None:
        credentials = workspace_git_credentials(workspace)
    log_path = backend_log_path(workspace)
    command = [*backend_start_command(port=port, project_dir=project_dir), *flags]
    spawn_detached(command, workspace=workspace, log_path=log_path, credentials=credentials)
    return _await_own_backend(port, workspace=workspace, log_path=log_path)


def _start_backend(port: int, *, workspace: Path, project_dir: Path | None) -> int:
    return start_detached(port, workspace=workspace, project_dir=project_dir)


def _await_own_backend(port: int, *, workspace: Path, log_path: Path) -> int:
    """Wait for the backend we just spawned — and for it to be ours.

    The port was free when the plan was made; confirming identity closes the window in which another
    workspace's backend claimed it in between, which would otherwise be reported as our own start
    succeeding.
    """
    claim = workspace_claim(workspace)
    deadline = time.monotonic() + STARTUP_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        state = read_backend_state(workspace)
        effective_port = state["port"] if state is not None else port
        if _is_own_backend_serving(effective_port, claim):
            logger.info("Backend became healthy on port %s", effective_port)
            return effective_port
        time.sleep(_STARTUP_POLL_SECONDS)

    raise RuntimeError(f"Timed out waiting for this workspace's backend on port {port}. See {log_path}.")


def _is_own_backend_serving(port: int, claim: WorkspaceClaim | None) -> bool:
    """A workspace that states no claim can only ask whether *something* answers."""
    if not probe_backend(port):
        return False
    return claim is None or port_serves_workspace(port, claim)
