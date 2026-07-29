"""Backend lifecycle control: status, stop, and ensure-running."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path

from src.infrastructure.backend.backend_probe import (
    backend_start_command,
    configured_backend_url,
    port_in_use,
    probe_backend,
    probe_backend_url,
    resolve_backend_port,
)
from src.infrastructure.backend.backend_process import (
    BackendInstance,
    _read_process_state,
    backend_process_diagnostics,
    find_arch_backend_instance_for_port,
    find_arch_backend_instances,
)
from src.infrastructure.backend.backend_state import (
    _process_exists,
    backend_log_path,
    read_backend_state,
    remove_backend_state,
)

logger = logging.getLogger(__name__)


def _wait_for_exit(pid: int, *, timeout_s: float, interval: float) -> bool:
    """Poll until ``pid`` is gone or ``timeout_s`` elapses. Returns whether it exited."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _process_exists(pid):
            return True
        time.sleep(interval)
    return False


def ensure_backend_running(
    *,
    port: int | None = None,
    start_if_missing: bool = True,
    cwd: Path | None = None,
    project_dir: Path | None = None,
) -> int:
    resolved_port = resolve_backend_port(start=cwd, explicit_port=port)
    state = read_backend_state(cwd)
    if state is not None:
        if probe_backend(state["port"]):
            logger.info("Reusing healthy backend on port %s", state["port"])
            return state["port"]
        if not _process_exists(state["pid"]):
            logger.warning("Removing stale backend state for pid %s", state["pid"])
            remove_backend_state(cwd)

    external_url = configured_backend_url()
    if external_url:
        if probe_backend_url(external_url):
            logger.info("Using externally configured backend at %s", external_url)
            return resolved_port
        raise RuntimeError(f"Configured external backend is not reachable: {external_url}")

    if not start_if_missing:
        raise RuntimeError("Unified backend is not running.")

    if cwd is None:
        cwd = Path.cwd()
    log_path = backend_log_path(cwd)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab") as log:
        command = backend_start_command(port=resolved_port, project_dir=project_dir)
        logger.info("Starting backend with command: %s", " ".join(command))
        subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        state = read_backend_state(cwd)
        effective_port = resolved_port
        if state is not None:
            effective_port = state["port"]
        if probe_backend(effective_port):
            logger.info("Backend became healthy on port %s", effective_port)
            return effective_port
        time.sleep(0.25)

    raise RuntimeError(f"Timed out waiting for unified backend on port {resolved_port}. See {log_path}.")


def _instance_status(instance: BackendInstance, port: int, log_path: object) -> dict[str, object]:
    """Build a status dict for an untracked arch-backend instance."""
    process_state = instance["process_state"]
    pid = instance["pid"]
    base = {
        "pid": pid,
        "port": port,
        "process_state": process_state,
        "stdin": instance["stdin"],
        "stdout": instance["stdout"],
        "stderr": instance["stderr"],
        "log_path": str(log_path),
    }
    if process_state in {"T", "t"}:
        logger.warning("arch-backend pid %s is stopped/suspended while still holding port %s", pid, port)
        return {"running": False, "reason": "stopped_backend", **base}
    if not probe_backend(port):
        logger.warning("arch-backend pid %s matched port %s but backend probe failed", pid, port)
        return {"running": False, "reason": "unhealthy_backend", **base}
    logger.info("arch-backend pid %s is healthy on port %s without state file", pid, port)
    return {"running": True, "reason": "ok_untracked", **base}


def backend_status(*, cwd: Path | None = None, port: int | None = None) -> dict[str, object]:
    resolved_port = resolve_backend_port(start=cwd, explicit_port=port)
    logger.info("Evaluating backend status for port %s (cwd=%s)", resolved_port, cwd or Path.cwd())
    log_path = backend_log_path(cwd)
    state = read_backend_state(cwd)
    if state is None:
        instance = find_arch_backend_instance_for_port(resolved_port)
        if instance is not None:
            return _instance_status(instance, resolved_port, log_path)
        if probe_backend(resolved_port):
            logger.warning(
                "Port %s responds to backend probe but is not identified as arch-backend",
                resolved_port,
            )
            return {"running": False, "reason": "unmanaged_backend", "port": resolved_port}
        if port_in_use(port=resolved_port):
            logger.warning("Port %s is in use by a non-backend or unidentifiable process", resolved_port)
            return {"running": False, "reason": "port_in_use", "port": resolved_port}
        logger.info("No backend is running on port %s", resolved_port)
        return {"running": False, "reason": "not_running"}

    pid = state["pid"]
    port = state["port"]
    if not _process_exists(pid):
        logger.warning("Removing stale backend state for missing pid %s", pid)
        remove_backend_state(cwd)
        return {"running": False, "reason": "stale_pid", "pid": pid, "port": port}

    process_state = _read_process_state(pid)
    diagnostics = backend_process_diagnostics(pid)
    if process_state in {"T", "t"}:
        logger.warning("Tracked arch-backend pid %s is stopped/suspended on port %s", pid, port)
        return {
            "running": False,
            "reason": "stopped_backend",
            "pid": pid,
            "port": port,
            "process_state": process_state,
            "stdin": diagnostics["stdin"],
            "stdout": diagnostics["stdout"],
            "stderr": diagnostics["stderr"],
            "log_path": str(log_path),
        }

    healthy = probe_backend(port)
    logger.info("Backend state file points to pid=%s port=%s healthy=%s", pid, port, healthy)
    return {
        "running": healthy,
        "reason": "ok" if healthy else "unhealthy",
        "pid": pid,
        "port": port,
        "process_state": process_state,
        "stdin": diagnostics["stdin"],
        "stdout": diagnostics["stdout"],
        "stderr": diagnostics["stderr"],
        "log_path": str(log_path),
    }


def _stop_pid(
    pid: int, *, cwd: Path | None = None, timeout_s: float = 5.0, port: int | None = None
) -> dict[str, object]:
    tracked_state = read_backend_state(cwd)
    tracked_pid = tracked_state["pid"] if tracked_state is not None else None
    process_state = _read_process_state(pid)
    logger.info(
        "Attempting to stop pid=%s on port=%s (tracked_pid=%s, cwd=%s, timeout_s=%.1f, process_state=%s)",
        pid,
        port,
        tracked_pid,
        cwd or Path.cwd(),
        timeout_s,
        process_state,
    )
    def _stale() -> dict[str, object]:
        if tracked_pid == pid:
            remove_backend_state(cwd)
        return {"stopped": False, "reason": "stale_pid", "pid": pid}

    def _exited() -> dict[str, object]:
        if tracked_pid == pid:
            remove_backend_state(cwd)
        return {"stopped": True, "pid": pid, "port": port}

    if process_state in {"T", "t"}:
        try:
            os.kill(pid, signal.SIGCONT)
            logger.info("Sent SIGCONT to stopped pid %s before termination", pid)
        except ProcessLookupError:
            logger.warning("SIGCONT target pid %s does not exist", pid)
            return _stale()
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        logger.warning("SIGTERM target pid %s does not exist", pid)
        return _stale()

    if _wait_for_exit(pid, timeout_s=timeout_s, interval=0.1):
        logger.info("pid %s exited after SIGTERM", pid)
        return _exited()

    logger.warning("Timed out waiting for pid %s to exit after SIGTERM; escalating to SIGKILL", pid)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        logger.info("pid %s exited before SIGKILL was delivered", pid)
        return _exited()

    if _wait_for_exit(pid, timeout_s=min(timeout_s, 2.0), interval=0.05):
        logger.info("pid %s exited after SIGKILL", pid)
        return _exited()

    logger.error("Timed out waiting for pid %s to exit even after SIGKILL", pid)
    return {"stopped": False, "reason": "timeout", "pid": pid, "port": port}


def _stop_all(pids: list[int], *, cwd: Path | None, timeout_s: float, port: int) -> dict[str, object]:
    """Stop every pid in ``pids`` (same-port backends), reporting which actually stopped."""
    logger.warning("Stopping all %d arch-backend instances on port %s: %s", len(pids), port, pids)
    stopped_pids = [
        pid for pid in pids if _stop_pid(pid, cwd=cwd, timeout_s=timeout_s, port=port).get("stopped")
    ]
    if stopped_pids:
        return {"stopped": True, "pid": stopped_pids[0], "pids": stopped_pids, "port": port}
    return {"stopped": False, "reason": "multiple_matching", "port": port, "pids": pids}


def stop_backend(*, cwd: Path | None = None, timeout_s: float = 5.0, port: int | None = None) -> dict[str, object]:
    resolved_port = resolve_backend_port(start=cwd, explicit_port=port)
    logger.info("Stop request for backend on port %s (cwd=%s)", resolved_port, cwd or Path.cwd())
    state = read_backend_state(cwd)
    if state is not None:
        pid = state["pid"]
        state_port = state["port"]
        logger.info("Existing backend state for stop request: %s", state)
        if state_port == resolved_port or not _process_exists(pid):
            return _stop_pid(pid, cwd=cwd, timeout_s=timeout_s, port=state_port)

    instances = find_arch_backend_instances()
    matches = [
        instance
        for instance in instances
        if resolved_port in instance["ports"] or instance["declared_port"] == resolved_port
    ]
    if len(matches) == 1:
        instance = matches[0]
        logger.info(
            "Stopping matched arch-backend instance pid=%s for port=%s",
            instance["pid"],
            resolved_port,
        )
        return _stop_pid(
            instance["pid"],
            cwd=cwd,
            timeout_s=timeout_s,
            port=resolved_port,
        )
    if len(matches) > 1:
        # Prefer the process that owns the listening socket; launcher wrappers
        # (e.g. ``uv run``) may share the declared port but not the socket.
        socket_owners = [m for m in matches if resolved_port in m["ports"]]
        if len(socket_owners) == 1:
            instance = socket_owners[0]
            logger.info(
                "Resolved multiple port matches to socket owner pid=%s for port=%s",
                instance["pid"],
                resolved_port,
            )
            result = _stop_pid(instance["pid"], cwd=cwd, timeout_s=timeout_s, port=resolved_port)
            # Terminate any declarants that claimed the port but don't own the socket (e.g. launcher wrappers).
            for m in matches:
                leftover_pid = m["pid"]
                if leftover_pid == instance["pid"]:
                    continue
                logger.info(
                    "Terminating leftover arch-backend declarant pid=%s for port=%s",
                    leftover_pid,
                    resolved_port,
                )
                try:
                    os.kill(leftover_pid, signal.SIGTERM)
                except ProcessLookupError:
                    continue
                except PermissionError:
                    # Best-effort cleanup: a declarant we cannot signal (not ours) must
                    # not abort the stop — the socket owner has already been terminated.
                    logger.warning("No permission to terminate declarant pid=%s; skipping", leftover_pid)
                    continue
                _wait_for_exit(leftover_pid, timeout_s=min(timeout_s, 3.0), interval=0.1)
            return result
        # Genuinely multiple backend instances on the same port — stop all.
        pids = [m["pid"] for m in (socket_owners or matches)]
        return _stop_all(pids, cwd=cwd, timeout_s=timeout_s, port=resolved_port)

    if len(instances) == 1:
        instance = instances[0]
        ports = instance["ports"]
        other_port = ports[0] if ports else instance["declared_port"]
        logger.warning(
            "Only one arch-backend instance exists, but it is on port %s instead of requested port %s (pid=%s)",
            other_port,
            resolved_port,
            instance["pid"],
        )
        return {
            "stopped": False,
            "reason": "single_other_port",
            "pid": instance["pid"],
            "port": other_port,
            "expected_port": resolved_port,
        }

    if state is None:
        logger.info("Stop request found no backend state and no matching arch-backend process")
        return {"stopped": False, "reason": "not_running"}

    remove_backend_state(cwd)
    return {"stopped": False, "reason": "stale_pid", "pid": state["pid"]}
