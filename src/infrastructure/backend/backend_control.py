"""Backend lifecycle control: what is running for *this* workspace, and stopping it.

Every question here is asked about one workspace, so every answer is scoped to it. An arch-backend
process on the machine is not this workspace's backend merely because it holds the port this
workspace would use: two checkouts ship the same default, so `--status` reported a neighbour's
backend as running and `--stop` would have signalled it. What a backend serves decides ownership;
the port only decides where to look.

Starting one lives in `backend_launch` — that is a different question ("which endpoint may this
workspace use"), and it is answered by a plan.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path

from src.infrastructure.backend.backend_endpoint import (
    foreign_occupant,
    instances_serving_workspace,
    workspace_claim,
)
from src.infrastructure.backend.backend_probe import (
    backend_port_preference,
    port_in_use,
    probe_backend,
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
from src.infrastructure.backend.shutdown import STOP_DEADLINE_SECONDS

logger = logging.getLogger(__name__)



def _wait_for_exit(pid: int, *, timeout_s: float, interval: float) -> bool:
    """Poll until ``pid`` is gone or ``timeout_s`` elapses. Returns whether it exited."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _process_exists(pid):
            return True
        time.sleep(interval)
    return False


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
    claim = workspace_claim(cwd)
    state = read_backend_state(cwd)
    if state is None:
        # "Is my backend running" comes before "what is on my preferred port". Our own backend may be
        # on a derived port with no record naming it — relocated because a neighbour held the default,
        # its record lost — and answering about the neighbour instead would report it as not running.
        own = instances_serving_workspace(find_arch_backend_instances(), claim)
        if len(own) == 1:
            ours = own[0]
            return _instance_status(ours, ours["ports"][0], log_path)
        instance = find_arch_backend_instance_for_port(resolved_port)
        if instance is not None:
            foreign = foreign_occupant(resolved_port, claim, pid=instance["pid"])
            return foreign if foreign is not None else _instance_status(instance, resolved_port, log_path)
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
    if healthy:
        # A record can outlive the port it names: the workspace's own backend died without clearing
        # it and a neighbour's took the socket. Answering "ok" then reports the neighbour.
        foreign = foreign_occupant(port, claim, pid=pid)
        if foreign is not None:
            return {**foreign, "process_state": process_state, "log_path": str(log_path)}
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


def _commanded_elsewhere(recorded_port: int, *, cwd: Path | None, explicit_port: int | None) -> bool:
    """Whether this invocation asked about a port other than the one this workspace recorded."""
    preference = backend_port_preference(start=cwd, explicit_port=explicit_port)
    return preference.authority == "command" and preference.port != recorded_port


def _stop_pid(
    pid: int, *, cwd: Path | None = None, timeout_s: float = STOP_DEADLINE_SECONDS,
    port: int | None = None,
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


def stop_backend(
    *, cwd: Path | None = None, timeout_s: float = STOP_DEADLINE_SECONDS, port: int | None = None,
) -> dict[str, object]:
    resolved_port = resolve_backend_port(start=cwd, explicit_port=port)
    logger.info("Stop request for backend on port %s (cwd=%s)", resolved_port, cwd or Path.cwd())
    claim = workspace_claim(cwd)
    state = read_backend_state(cwd)
    if state is not None:
        pid = state["pid"]
        state_port = state["port"]
        logger.info("Existing backend state for stop request: %s", state)
        # The record names this workspace's backend wherever it ended up, which need not be the
        # preferred port: a workspace whose default was taken serves on a derived one. Only a port
        # named on this command line overrides the record — comparing against the *resolved* port
        # instead left `--stop` unable to stop a relocated backend at all.
        if not _commanded_elsewhere(state_port, cwd=cwd, explicit_port=port) or not _process_exists(pid):
            return _stop_pid(pid, cwd=cwd, timeout_s=timeout_s, port=state_port)

    instances = find_arch_backend_instances()
    own = instances_serving_workspace(instances, claim)
    if len(own) == 1:
        # Ours, on a port no record pointed at. It needs no confirmation prompt: the backend said it
        # serves this workspace's repositories, which is the whole question a prompt would ask. This
        # precedes the foreign check, or a neighbour on the preferred port hides our own from a stop.
        ours = own[0]
        own_port = ours["ports"][0]
        logger.info("Stopping this workspace's backend pid=%s on port %s", ours["pid"], own_port)
        return _stop_pid(ours["pid"], cwd=cwd, timeout_s=timeout_s, port=own_port)

    foreign = foreign_occupant(resolved_port, claim)
    if foreign is not None:
        return {
            "stopped": False,
            "reason": "foreign_workspace",
            "port": resolved_port,
            "served_roots": foreign["served_roots"],
        }

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
        # The one backend on the machine may be a neighbour's. Reporting it as "yours, on another
        # port" invites the operator to go and stop something that is not theirs.
        elsewhere = foreign_occupant(other_port, claim) if isinstance(other_port, int) else None
        if elsewhere is not None:
            return {
                "stopped": False,
                "reason": "foreign_workspace",
                "port": other_port,
                "served_roots": elsewhere["served_roots"],
            }
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

    if _process_exists(state["pid"]):
        # The record names a live process on a port this request did not ask about — which happens
        # when `--port` names another one. Calling that record stale and deleting it would lose the
        # only pointer to a running backend, on the strength of a question about somewhere else.
        logger.info(
            "Record names a live backend pid=%s on port %s; this request asked about port %s",
            state["pid"], state["port"], resolved_port,
        )
        return {
            "stopped": False,
            "reason": "single_other_port",
            "pid": state["pid"],
            "port": state["port"],
            "expected_port": resolved_port,
        }

    remove_backend_state(cwd)
    return {"stopped": False, "reason": "stale_pid", "pid": state["pid"]}
