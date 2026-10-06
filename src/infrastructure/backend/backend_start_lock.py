"""One start of a workspace's backend at a time.

A backend is not answering for the seconds it spends building its index, and nothing about it — a
port, a record, a probe — distinguishes that from a backend that has hung. Two starters that look in
that window disagree with each other: two stdio bridges configured against one workspace both found
nothing serving on a cold start, both spawned a backend, and the second backend's pre-start guard
found the first one's process holding the port without answering and refused, calling it unhealthy.

So a starter holds this lock from the moment it plans until its backend serves, and a second starter
waits for it and then plans again — which now finds the first one's backend and attaches. The lock is
an `flock` on a file in the workspace's state directory: the kernel releases it when the holding
process exits, so a starter that crashed leaves nothing behind to clear by hand.

Taken by starters only: the bridges (`ensure_backend_running`), `arch-backend --daemon`, and the
updater's restart. Never by the serving process itself, which a lock holder spawns and waits for.
"""

from __future__ import annotations

import fcntl
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from src.infrastructure.backend.backend_state import backend_start_lock_path

logger = logging.getLogger(__name__)

_POLL_SECONDS = 0.1


@contextmanager
def backend_start_lock(workspace: Path, *, timeout_s: float) -> Iterator[None]:
    """Hold this workspace's start lock, waiting up to *timeout_s* for another starter to finish.

    Raises `RuntimeError` naming the holder's pid when the wait runs out, rather than starting a
    second backend beside one that is still coming up.
    """
    path = backend_start_lock_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as handle:
        _acquire(handle, path, timeout_s=timeout_s)
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _acquire(handle: IO[str], path: Path, *, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    waited = False
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if waited:
                logger.info("Another start of this workspace's backend finished; planning again")
            return
        except BlockingIOError:
            if not waited:
                logger.info("Another process is starting this workspace's backend; waiting for it")
                waited = True
            if time.monotonic() >= deadline:
                handle.seek(0)
                holder = handle.read().strip() or "unknown"
                raise RuntimeError(
                    f"Another process (pid {holder}) has been starting this workspace's backend for "
                    f"over {timeout_s:.0f} seconds; see the backend log beside {path}."
                ) from None
            time.sleep(_POLL_SECONDS)
