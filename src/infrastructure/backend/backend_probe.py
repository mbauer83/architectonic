"""HTTP probing, port resolution, and workspace config for the arch backend."""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import socket
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from src.config.settings import backend_port as global_backend_port

logger = logging.getLogger(__name__)


def load_workspace_config(start: Path | None = None) -> dict | None:
    """Load arch-workspace.yaml from *start* or any parent directory. Returns None if not found."""
    import yaml

    search = start or Path.cwd()
    for candidate in [search, *search.parents]:
        cfg = candidate / "arch-workspace.yaml"
        if cfg.exists():
            try:
                data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else None
            except Exception:  # noqa: BLE001
                return None
    return None


def resolve_backend_port(*, start: Path | None = None, explicit_port: int | None = None) -> int:
    if explicit_port is not None:
        logger.info("Using explicit backend port %s", explicit_port)
        return explicit_port

    cfg = load_workspace_config(start)
    if cfg is not None:
        port = cfg.get("backend", {}).get("port")
        if isinstance(port, int):
            logger.info("Using backend port %s from arch-workspace.yaml", port)
            return port

    resolved = global_backend_port()
    logger.info("Using backend port %s from config/settings.yaml", resolved)
    return resolved


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


def port_in_use(*, host: str = "127.0.0.1", port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError as exc:
        logger.warning("Unable to open socket while checking port %s: %s", port, exc)
        return False
    try:
        sock.settimeout(0.5)
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
