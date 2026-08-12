"""Keeping the backend's own log bounded, from the process whose descriptors point at it.

**Why not `RotatingFileHandler`.** The log is not written through a logging handler. `arch-backend
--daemon` hands its child a stdout and stderr that already point at `.arch/backend.log`, so
everything the process emits reaches the file by *file descriptor*: logging records, uvicorn's own
output, a traceback from an interpreter shutdown, a print from a dependency. A handler would rotate
only the records it formats and leave every other writer appending to the renamed inode — which is
the same file, under a name nobody looks at, still growing.

So rotation is done where the descriptors are owned: rename the generations, then point stdout and
stderr at the fresh file. `.arch/backend.log` reached **62 MB over 491,225 lines** on a development
box and had to be truncated by hand, which is the whole reason this exists.

**Only the log this process is writing to.** A foreground `arch-backend` on a terminal has stdout on
the tty, and renaming a file it never writes to — then redirecting its output into the replacement —
would take the operator's console away. Every entry point here checks the descriptor first.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from src.config.settings import backend_log_generations, backend_log_max_bytes

logger = logging.getLogger(__name__)

#: How often the size is checked. The bound this yields is the threshold plus one interval's writes:
#: at the rate that produced the 62 MB file (~40 KB a minute) that overshoot is immaterial, and a
#: shorter interval would only stat the same file more often on an idle backend.
CHECK_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True)
class RotationPolicy:
    """When to rotate, and how much history to keep afterwards."""

    max_bytes: int
    generations: int

    @property
    def bounded_at_bytes(self) -> int:
        """The most this log costs on disk, live file and kept generations together."""
        return self.max_bytes * (self.generations + 1)


def policy_from_settings() -> RotationPolicy:
    return RotationPolicy(max_bytes=backend_log_max_bytes(), generations=backend_log_generations())


def point_output_at(log_path: Path) -> None:
    """Make this process's stdout and stderr the file at *log_path*, at the descriptor level.

    Used both when a process first adopts the log and after each rotation, so "the output goes to
    this file" has one definition rather than one per caller.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.dup2(log_fd, sys.stdout.fileno())
        os.dup2(log_fd, sys.stderr.fileno())
    finally:
        if log_fd > 2:
            os.close(log_fd)


def output_goes_to(log_path: Path) -> bool:
    """Whether this process's stdout *is* that file — not a terminal, a pipe, or another log."""
    try:
        written = os.fstat(sys.stdout.fileno())
        target = log_path.stat()
    except (OSError, ValueError):
        return False
    return (written.st_dev, written.st_ino) == (target.st_dev, target.st_ino)


def rotate_if_oversized(log_path: Path, policy: RotationPolicy) -> bool:
    """Rotate when the log has outgrown the policy, and report whether it did."""
    if not output_goes_to(log_path):
        return False
    try:
        size = log_path.stat().st_size
    except OSError:
        return False
    if size < policy.max_bytes:
        return False
    _shift_generations(log_path, policy.generations)
    point_output_at(log_path)
    # After re-pointing, so the record of the rotation is in the file that follows it rather than in
    # the one that was just closed.
    logger.info(
        "Rotated the backend log at %d bytes; keeping %d generation(s), bounded at %d bytes",
        size, policy.generations, policy.bounded_at_bytes,
    )
    return True


def keep_bounded(
    log_path: Path,
    policy: RotationPolicy,
    *,
    interval_s: float = CHECK_INTERVAL_SECONDS,
) -> threading.Event:
    """Rotate this process's log for as long as it runs. Returns the event that stops the checking.

    A daemon thread, and deliberately not a teardown obligation: rotation holds nothing durable, so a
    process on its way out owes it nothing. It is started by the entry point that owns the process's
    descriptors, never from the application object — a `TestClient` building the same app must not
    acquire a thread that redirects the developer's terminal.
    """
    stopping = threading.Event()

    def check_periodically() -> None:
        while not stopping.wait(interval_s):
            try:
                rotate_if_oversized(log_path, policy)
            except OSError as exc:
                logger.warning("Could not rotate the backend log at %s: %s", log_path, exc)

    threading.Thread(target=check_periodically, name="backend-log-rotation", daemon=True).start()
    return stopping


def _shift_generations(log_path: Path, generations: int) -> None:
    """`backend.log` → `.log.1`, `.log.1` → `.log.2`, and what falls past the last is dropped."""
    _generation(log_path, generations).unlink(missing_ok=True)
    for index in range(generations - 1, 0, -1):
        source = _generation(log_path, index)
        if source.exists():
            source.rename(_generation(log_path, index + 1))
    log_path.rename(_generation(log_path, 1))


def _generation(log_path: Path, index: int) -> Path:
    return log_path.with_name(f"{log_path.name}.{index}")
