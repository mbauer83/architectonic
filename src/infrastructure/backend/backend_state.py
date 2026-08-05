"""State file I/O and path resolution for the arch backend."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TypedDict

from src.config.settings import backend_log_path as configured_backend_log_path
from src.infrastructure.backend.backend_process import _read_process_state
from src.infrastructure.workspace.workspace_init import load_init_state

BACKEND_STATE_FILENAME = "backend.pid"
BACKEND_LOG_FILENAME = "backend.log"
logger = logging.getLogger(__name__)


class BackendState(TypedDict):
    pid: int
    port: int


def workspace_root(start: Path | None = None) -> Path | None:
    state = load_init_state(start)
    if state and state.get("workspace_root"):
        return Path(str(state["workspace_root"])).resolve()
    return None


def _state_dir(start: Path | None = None) -> Path:
    env_dir = os.getenv("ARCH_BACKEND_STATE_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    root = workspace_root(start)
    if root is not None:
        return root / ".arch"

    base = (start or Path.cwd()).resolve()
    if base.is_file():
        base = base.parent
    return base / ".arch"


def backend_state_path(start: Path | None = None) -> Path:
    return _state_dir(start) / BACKEND_STATE_FILENAME


def backend_log_path(start: Path | None = None) -> Path:
    configured = Path(configured_backend_log_path()).expanduser()
    if configured.is_absolute():
        return configured

    root = workspace_root(start)
    if root is not None:
        return (root / configured).resolve()

    base = (start or Path.cwd()).resolve()
    if base.is_file():
        base = base.parent
    return (base / configured).resolve()


def read_backend_state(start: Path | None = None) -> BackendState | None:
    path = backend_state_path(start)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    pid = data.get("pid")
    port = data.get("port")
    if not isinstance(pid, int) or not isinstance(port, int):
        return None
    return BackendState(pid=pid, port=port)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie still answers the signal probe but is already dead: it serves
    # nothing and holds no port — only its unreaped exit status lingers, and no
    # signal (not even SIGKILL) can make it exit. Counting it as alive makes
    # stop_backend wait out its full timeout and report a false failure.
    state = _read_process_state(pid)
    return state is None or state not in ("Z", "X")


def write_backend_state(*, port: int, pid: int | None = None, start: Path | None = None) -> Path:
    path = backend_state_path(start)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"pid": pid or os.getpid(), "port": port}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def remove_backend_state(start: Path | None = None) -> None:
    path = backend_state_path(start)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def remove_own_backend_state(start: Path | None = None) -> None:
    """Drop the record only if it names *this* process.

    A serving backend's record is the workspace's pointer to it, and any process running in the
    workspace resolves the same path — so an unconditional delete on the way out lets a short-lived
    one (a test driving the entry point, a wrapper that got as far as the teardown) orphan a live
    backend. `--status` then has to fall back to identifying it by what it serves, and `--stop` had no
    pointer at all. Exiting means "remove my record", never "remove whatever record is here".
    """
    state = read_backend_state(start)
    if state is None:
        return
    if state["pid"] != os.getpid():
        logger.info(
            "Leaving backend state for pid %s in place: this process is %s", state["pid"], os.getpid()
        )
        return
    remove_backend_state(start)
