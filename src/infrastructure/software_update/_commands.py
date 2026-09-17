"""One way to run a tool of the checkout — `uv run --project <checkout> …` — and read its answer."""

from __future__ import annotations

import subprocess
from pathlib import Path

#: `uv run` re-locks and re-syncs a project whose `pyproject.toml` changed unless told not to. The
#: updater owns both: a re-lock after the version bump would dirty the checkout, and a re-sync would
#: drop every group and extra the derived selection installed.
UV_RUN_FLAGS = ("--frozen", "--no-sync")


class CommandFailed(RuntimeError):
    def __init__(self, doing: str, returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(f"{doing} failed ({returncode}): {stderr.strip()[-2000:] or stdout.strip()[-2000:]}")
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run_command(command: list[str], *, cwd: Path, timeout: int, doing: str) -> subprocess.CompletedProcess[str]:
    """Run `command`, returning whatever it exited with; only a failure to run at all raises."""
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CommandFailed(doing, -1, "", str(exc)) from exc


def run_checked(command: list[str], *, cwd: Path, timeout: int, doing: str) -> str:
    """Run `command` and return its stdout; any non-zero exit is `CommandFailed`."""
    result = run_command(command, cwd=cwd, timeout=timeout, doing=doing)
    if result.returncode != 0:
        raise CommandFailed(doing, result.returncode, result.stdout, result.stderr)
    return result.stdout


def checkout_tool(uv: str, checkout: Path, tool: str, *arguments: str) -> list[str]:
    """`tool` as the checkout's own version runs it, whatever the calling process is."""
    return [uv, "run", *UV_RUN_FLAGS, "--project", str(checkout), tool, *arguments]
