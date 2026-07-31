"""What ``arch-backend --status``, ``--stop`` and ``--restart`` print, ask and exit with.

Split from the entry point because it is presentation, not lifecycle: ``backend_control`` decides
what happens to a process, and this decides what the operator is told about it. Keeping the two
together made the entry point the longest file in the package and buried the one place a human is
asked to confirm stopping something.

Nothing here chooses a deadline or sends a signal — see ``backend.shutdown`` for the stop contract.

``backend_control`` is called through the module rather than by imported name, deliberately: the
name form binds at import, so a caller in one module and a stub applied to another silently miss
each other — which is how a test meaning to stub the lifecycle layer reached a *live* backend
process instead. One seam, wherever the command happens to live.
"""

from __future__ import annotations

import argparse
import sys

from src.infrastructure.backend import backend_control

# ── Status command ────────────────────────────────────────────────────────────

def _status_headline(result: dict) -> str:
    """One-line status summary derived from the backend_status result."""
    p, pid = result.get("port"), result.get("pid")
    if result.get("running"):
        return f"backend is running on port {p} (pid {pid})"
    messages: dict[object, str] = {
        "unmanaged_backend": f"backend responding on port {p} but not managed by this workspace",
        "port_in_use": f"port {p} is in use by another process",
        "not_running": "backend is not running",
        "stopped_backend": f"backend process pid {pid} is stopped on port {p}",
        "unhealthy_backend": f"backend process pid {pid} is not responding on port {p}",
        "stale_pid": f"removed stale backend pid {pid}",
        "invalid_state": "backend state is invalid",
    }
    return messages.get(result.get("reason"), f"backend is not healthy on port {p} (pid {pid})")


def _run_status(resolved_port: int) -> None:
    result = backend_control.backend_status(port=resolved_port)
    print(_status_headline(result))
    if ps := result.get("process_state"):
        print(f"  process state: {ps}")
    if stdio := " ".join(f"{k}={result[k]}" for k in ("stdin", "stdout", "stderr") if result.get(k) is not None):
        print(f"  stdio: {stdio}")
    if lp := result.get("log_path"):
        print(f"  log: {lp}")

# ── Stop command ──────────────────────────────────────────────────────────────

def _run_stop(args: argparse.Namespace, resolved_port: int) -> None:
    result = backend_control.stop_backend(port=resolved_port)
    reason = result.get("reason")
    if result.get("stopped"):
        _print_stopped(result)
    elif reason == "not_running":
        print("backend is not running")
    elif reason == "stale_pid":
        print(f"removed stale backend pid {result.get('pid')}")
    elif reason == "invalid_state":
        print("removed invalid backend state")
    elif reason == "single_other_port":
        pid = result.get("pid")
        if not isinstance(pid, int):
            raise SystemExit("failed to determine backend pid")
        other_port = result.get("port")
        if _confirm_stop_other_instance(expected_port=resolved_port, pid=pid, actual_port=other_port):
            follow_up = backend_control.stop_backend(port=int(other_port) if isinstance(other_port, int) else None)
            if follow_up.get("stopped"):
                _print_stopped(follow_up)
            else:
                raise SystemExit(f"failed to stop backend pid {follow_up.get('pid')}")
        else:
            raise SystemExit(1)
    else:
        raise SystemExit(f"failed to stop backend pid {result.get('pid')}")


def _print_stopped(result: dict) -> None:
    pids = result.get("pids")
    if isinstance(pids, list) and len(pids) > 1:
        print(f"stopped backend pids {', '.join(str(p) for p in pids)}")
    else:
        print(f"stopped backend pid {result.get('pid')}")


def _confirm_stop_other_instance(*, expected_port: int, pid: int, actual_port: object) -> bool:
    if not sys.stdin.isatty():
        print(f"found arch-backend on port {actual_port} (pid {pid}); configured port is {expected_port}. "
              f"Rerun interactively or pass --port {actual_port}")
        return False
    try:
        return input(f"Backend on port {actual_port} (pid {pid}), configured port is {expected_port}. "
                     f"Stop it? [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def _stop_for_restart(resolved_port: int) -> None:
    result = backend_control.stop_backend(port=resolved_port)
    if result.get("stopped"):
        _print_stopped(result)
    elif result.get("reason") not in {"not_running", "stale_pid", "invalid_state"}:
        raise SystemExit(f"failed to restart backend pid {result.get('pid')}")
