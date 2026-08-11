"""HTTP probing, port resolution, and workspace config for the arch backend."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import socket
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.config.settings import backend_port as global_backend_port
from src.domain.deployment.backend_endpoint import BackendIdentity, PortPreference
from src.domain.yaml_documents import parse_yaml

logger = logging.getLogger(__name__)

#: Names the port for one run, ahead of every configuration file.
ENV_BACKEND_PORT = "ARCH_BACKEND_PORT"


def load_workspace_config(start: Path | None = None) -> dict | None:
    """Load arch-workspace.yaml from *start* or any parent directory. Returns None if not found."""

    search = start or Path.cwd()
    for candidate in [search, *search.parents]:
        cfg = candidate / "arch-workspace.yaml"
        if cfg.exists():
            try:
                data = parse_yaml(cfg.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else None
            except Exception:  # noqa: BLE001
                return None
    return None


def backend_port_preference(
    *, start: Path | None = None, explicit_port: int | None = None
) -> PortPreference:
    """The port this workspace wants, and who said so.

    The authority matters as much as the number: a port named for this run or this workspace is a
    statement that is obeyed or refused, while the settings document ships the same default in every
    clone and is therefore a preference a second instance may yield. Without that distinction the
    two are indistinguishable, and yielding on a stated port is as wrong as dying on a default one.
    """
    if explicit_port is not None:
        logger.info("Using explicit backend port %s", explicit_port)
        return PortPreference(port=explicit_port, authority="command")

    env_port = os.getenv(ENV_BACKEND_PORT, "").strip()
    if env_port:
        try:
            return PortPreference(port=int(env_port), authority="environment")
        except ValueError:
            logger.warning("Ignoring non-numeric %s=%r", ENV_BACKEND_PORT, env_port)

    cfg = load_workspace_config(start)
    if cfg is not None:
        port = cfg.get("backend", {}).get("port")
        if isinstance(port, int):
            logger.info("Using backend port %s from arch-workspace.yaml", port)
            return PortPreference(port=port, authority="workspace_config")

    resolved = global_backend_port()
    logger.info("Using backend port %s from config/settings.yaml", resolved)
    return PortPreference(port=resolved, authority="settings_document")


def resolve_backend_port(*, start: Path | None = None, explicit_port: int | None = None) -> int:
    """The preferred port alone, for callers with nothing to decide about its authority."""
    return backend_port_preference(start=start, explicit_port=explicit_port).port


def backend_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def configured_backend_url() -> str | None:
    raw = os.getenv("ARCH_MCP_BACKEND_URL", "").strip()
    return raw.rstrip("/") if raw else None


def probe_backend_url(url: str, *, timeout_s: float = 1.0) -> bool:
    req = Request(f"{url.rstrip('/')}/api/stats", headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            logger.debug("Backend probe to %s returned HTTP %s", url, resp.status)
            return 200 <= resp.status < 500
    except (OSError, ValueError) as exc:
        logger.debug("Backend probe to %s failed: %s", url, exc)
        return False


def probe_backend(port: int, *, timeout_s: float = 1.0) -> bool:
    return probe_backend_url(backend_url(port), timeout_s=timeout_s)


def probe_backend_identity(base_url: str, *, timeout_s: float = 1.0) -> BackendIdentity | None:
    """What the backend at `base_url` says it serves, via `GET /api/backend-identity`.

    None on any failure — nothing there, an older backend without the endpoint, or a response that
    is not an identity. Every caller must treat that as "cannot confirm", never as "not ours" or
    "ours": both the upgrade guard and the endpoint planner fail closed on it, for the same reason.
    """
    req = Request(
        f"{base_url.rstrip('/')}/api/backend-identity",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            if not (200 <= resp.status < 300):
                return None
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, URLError):
        return None
    roots = payload.get("repo_roots")
    version = payload.get("software_version")
    if not isinstance(roots, list) or not isinstance(version, str):
        return None
    return BackendIdentity(repo_roots=tuple(str(r) for r in roots), software_version=version)


def probe_identity_on_port(port: int, *, timeout_s: float = 1.0) -> BackendIdentity | None:
    return probe_backend_identity(backend_url(port), timeout_s=timeout_s)


def port_in_use(*, host: str = "127.0.0.1", port: int, timeout_s: float = 0.5) -> bool:
    """Whether anything is listening on `port` — one connect attempt, no HTTP.

    `timeout_s` is worth passing when several ports are checked in a row: a listening loopback socket
    accepts in microseconds, but a *closed* one does not always refuse — on WSL2 the SYN is dropped, so
    every free port costs the whole timeout. Scanning nine candidates at the default is seconds of
    waiting for an answer that was available immediately.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError as exc:
        logger.warning("Unable to open socket while checking port %s: %s", port, exc)
        return False
    try:
        sock.settimeout(timeout_s)
        return sock.connect_ex((host, port)) == 0
    except OSError as exc:
        logger.warning("Unable to probe port %s on host %s: %s", port, host, exc)
        return False
    finally:
        sock.close()


def backend_start_command(*, port: int, project_dir: Path | None = None) -> list[str]:
    if importlib.util.find_spec("fastapi") and importlib.util.find_spec("uvicorn"):
        return [sys.executable, "-m", "src.infrastructure.backend.arch_backend", "--port", str(port)]

    uv = shutil.which("uv")
    if uv and project_dir is not None and (project_dir / "pyproject.toml").exists():
        # `gui` is a [dependency-groups] entry, so it is reached with --group; --extra names
        # [project.optional-dependencies] and uv rejects a selector it cannot find. This
        # fallback exists precisely for an environment without fastapi, so naming the wrong
        # kind of selector would leave it unable to start a backend at all.
        return [
            uv,
            "run",
            "--project",
            str(project_dir),
            "--group",
            "gui",
            "arch-backend",
            "--port",
            str(port),
        ]

    return [sys.executable, "-m", "src.infrastructure.backend.arch_backend", "--port", str(port)]


#: How long to keep waiting for a starting backend that is still alive but not yet answering.
#: A backstop against a process that hangs without exiting — deliberately not a prediction of
#: startup time, which is what the fixed 15s deadline it replaced was, and got wrong.
DAEMON_BACKSTOP_SECONDS = 600.0

StartupVerdict = Literal["serving", "exited", "backstop"]


def await_backend_startup(
    is_serving: Callable[[], bool],
    is_alive: Callable[[], bool],
    *,
    backstop_s: float = DAEMON_BACKSTOP_SECONDS,
    poll_s: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> StartupVerdict:
    """Wait for a starting backend, bounded by *the process*, not by a guess at how long it takes.

    The index is built by scanning every model file on every boot, so startup time is a function of
    the repository's size. A fixed deadline therefore encodes a corpus size, and reports a *false
    failure* for any repository larger than whoever chose the number imagined: measured at roughly
    1.1 ms per file, the 15 seconds this replaced ran out at about 13,600 files, while the backend
    it declared failed went on to serve normally.

    The process itself answers the question the deadline was guessing at. A child that is still
    alive is still starting, and one that has exited has failed — which is also detected *at once*
    rather than after the timeout, so a backend that dies on a bad config no longer costs a wait.
    ``backstop_s`` catches only the remaining case, a process that neither serves nor exits.
    """
    deadline = now() + backstop_s
    while now() < deadline:
        if is_serving():
            return "serving"
        if not is_alive():
            # Re-probe once: a backend that became ready and exited between the two checks would
            # otherwise be reported as a failure on the strength of check order alone.
            return "serving" if is_serving() else "exited"
        sleep(poll_s)
    return "backstop"
