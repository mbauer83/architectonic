"""Linux /proc-based process detection for arch-backend instances."""

from __future__ import annotations

import logging
import os
import pathlib
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)
_PROC_DIR = Path("/proc")


class ProcessDiagnostics(TypedDict):
    process_state: str | None
    ports: list[int]
    stdin: str | None
    stdout: str | None
    stderr: str | None
    argv: list[str]


class BackendInstance(TypedDict):
    pid: int
    argv: list[str]
    ports: list[int]
    declared_port: int | None
    process_state: str | None
    stdin: str | None
    stdout: str | None
    stderr: str | None


def _read_cmdline(pid: int) -> list[str]:
    try:
        raw = (_PROC_DIR / str(pid) / "cmdline").read_bytes()
    except OSError:
        return []
    return [part for part in raw.decode("utf-8", errors="replace").split("\x00") if part]


def _read_process_state(pid: int) -> str | None:
    try:
        stat = (_PROC_DIR / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return stat.rsplit(") ", 1)[1].split(" ", 1)[0]
    except IndexError:
        return None


def _parse_cli_port(argv: list[str]) -> int | None:
    for idx, arg in enumerate(argv):
        if arg == "--port" and idx + 1 < len(argv):
            try:
                return int(argv[idx + 1])
            except ValueError:
                return None
    return None


def _matches_arch_backend_process(argv: list[str]) -> bool:
    """Return True only when the process IS arch-backend, not when it merely launched one.

    ``uv run ... arch-backend ...`` is intentionally excluded: the process is ``uv``,
    not the backend itself.  Only Python or the arch-backend binary qualify.
    """
    if not argv:
        return False
    argv0 = pathlib.PurePath(argv[0]).name
    # Direct binary: arch-backend
    if argv0 == "arch-backend":
        return True
    # Python interpreter running arch-backend
    if argv0.startswith("python"):
        if len(argv) < 2:
            return False
        # python -m src.infrastructure.backend.arch_backend …
        if (
            argv[1] == "-m"
            and len(argv) >= 3
            and argv[2] in ("src.infrastructure.backend.arch_backend", "arch_backend")
        ):
            return True
        # python /path/to/arch-backend … (script path, not module)
        if pathlib.PurePath(argv[1]).name == "arch-backend":
            return True
        # python /path/to/arch_backend.py …
        if any(arg.endswith("src/tools/arch_backend.py") for arg in argv[1:3]):
            return True
    return False


def _list_listening_socket_inodes() -> dict[str, int]:
    inode_to_port: dict[str, int] = {}
    for proc_path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(proc_path).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 10 or parts[3] != "0A":
                continue
            local_address = parts[1]
            inode = parts[9]
            try:
                port = int(local_address.split(":")[1], 16)
            except (IndexError, ValueError):
                continue
            inode_to_port[inode] = port
    return inode_to_port


def _ports_for_pid(pid: int, inode_to_port: dict[str, int]) -> list[int]:
    fd_dir = _PROC_DIR / str(pid) / "fd"
    ports: set[int] = set()
    try:
        for fd_path in fd_dir.iterdir():
            try:
                target = os.readlink(fd_path)
            except OSError:
                continue
            if not target.startswith("socket:[") or not target.endswith("]"):
                continue
            inode = target[8:-1]
            port = inode_to_port.get(inode)
            if port is not None:
                ports.add(port)
    except OSError:
        return []
    return sorted(ports)


def _fd_target(pid: int, fd: int) -> str | None:
    try:
        return os.readlink(_PROC_DIR / str(pid) / "fd" / str(fd))
    except OSError:
        return None


def backend_process_diagnostics(pid: int) -> ProcessDiagnostics:
    inode_to_port = _list_listening_socket_inodes()
    return {
        "process_state": _read_process_state(pid),
        "ports": _ports_for_pid(pid, inode_to_port),
        "stdin": _fd_target(pid, 0),
        "stdout": _fd_target(pid, 1),
        "stderr": _fd_target(pid, 2),
        "argv": _read_cmdline(pid),
    }


def find_arch_backend_instances() -> list[BackendInstance]:
    inode_to_port = _list_listening_socket_inodes()
    candidates: list[BackendInstance] = []
    current_pid = os.getpid()
    try:
        proc_entries = [entry for entry in _PROC_DIR.iterdir() if entry.name.isdigit()]
    except OSError:
        return []
    proc_entries.sort(key=lambda path: int(path.name))
    for entry in proc_entries:
        pid = int(entry.name)
        if pid == current_pid:
            continue
        argv = _read_cmdline(pid)
        if not _matches_arch_backend_process(argv):
            continue
        candidates.append(
            {
                "pid": pid,
                "argv": argv,
                "ports": _ports_for_pid(pid, inode_to_port),
                "declared_port": _parse_cli_port(argv),
                "process_state": _read_process_state(pid),
                "stdin": _fd_target(pid, 0),
                "stdout": _fd_target(pid, 1),
                "stderr": _fd_target(pid, 2),
            }
        )
    logger.debug(
        "Detected %d arch-backend process candidate(s): %s",
        len(candidates),
        [
            {
                "pid": candidate["pid"],
                "ports": candidate["ports"],
                "declared_port": candidate["declared_port"],
                "process_state": candidate["process_state"],
            }
            for candidate in candidates
        ],
    )
    return candidates


def find_arch_backend_instance_for_port(port: int) -> BackendInstance | None:
    matches = [
        instance
        for instance in find_arch_backend_instances()
        if port in instance["ports"] or instance["declared_port"] == port
    ]
    if len(matches) == 1:
        logger.info(
            "Matched arch-backend pid %s for port %s (state=%s, ports=%s, declared_port=%s)",
            matches[0]["pid"],
            port,
            matches[0]["process_state"],
            matches[0]["ports"],
            matches[0]["declared_port"],
        )
        return matches[0]
    if len(matches) > 1:
        logger.warning(
            "Multiple arch-backend candidates matched port %s: %s",
            port,
            [m["pid"] for m in matches],
        )
    else:
        logger.info("No arch-backend process candidate matched port %s", port)
    return None
