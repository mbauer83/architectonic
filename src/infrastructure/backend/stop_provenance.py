"""Who asked the backend to stop — written where someone reading the backend's log will find it.

A backend that stopped cleanly leaves a perfect record of *how*: every teardown step, in order,
completing. It leaves nothing at all about *why*, and the two questions have different owners. The
teardown is the backend's. The reason is the stopper's, and a stopper is a separate process whose
logger writes to its own stderr — a CLI invocation that has since scrolled away, or a test's captured
output that was discarded. Twice in one session a backend stopped and nothing anywhere could say what
asked it to.

So a stop request records itself in the backend's own log before the signal is sent. Two lines
together then answer the question: this one names the process that asked, and the one the backend
writes as the signal lands names the signal and whether its parent is still alive. Their *absence* is
informative too — a backend that drained with no stop request recorded above it was stopped by
something that is not this project's tooling.

Best effort by construction. A stop must not fail because a log could not be written, so every error
here is swallowed: an unwritable path, a read-only mount, a workspace whose `.arch` does not exist
yet. The record is evidence, not a durability guarantee.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.infrastructure.backend.backend_state import backend_log_path


def record_stop_request(*, cwd: Path | None, port: int, target_pid: int | None = None) -> None:
    """Append a line to the workspace's backend log naming this process as the one asking.

    The command line as well as the pid, because a pid is only useful while the process still
    exists — and by the time anyone reads this, it will not.
    """
    line = (
        f"{datetime.now(timezone.utc).astimezone():%Y-%m-%d %H:%M:%S,%f}"[:-3]
        + " INFO  src.infrastructure.backend.stop_provenance: STOP REQUESTED"
        + f" port={port}"
        + (f" target_pid={target_pid}" if target_pid is not None else "")
        + f" by_pid={os.getpid()} by_ppid={os.getppid()}"
        + f" cwd={Path.cwd()}"
        + f" argv={' '.join(sys.argv)!r}\n"
    )
    _append(cwd, line)


def _append(cwd: Path | None, line: str) -> None:
    try:
        path = backend_log_path(cwd)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write(line)
    except Exception:  # noqa: BLE001 — evidence is never worth failing a stop over
        return
