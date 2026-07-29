"""Debounced background-refresh worker queue.

Extracted from context.py purely to keep that file under the LoC cap: this module owns the
queue/thread machinery only. It has no dependency on context.py's repo-resolution or
apply/refresh logic — those are passed in as callables — so the split stays one-way (context.py
imports this module, never the reverse) and avoids a circular import.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.application.read_models import ReadModelVersion

REFRESH_DEBOUNCE_S = 0.20


@dataclass
class RefreshQueue:
    cond: threading.Condition
    pending_full: bool = False
    pending_paths: set[Path] | None = None
    next_due_monotonic: float = 0.0
    worker: threading.Thread | None = None


_queues: dict[str, RefreshQueue] = {}
_queues_mu = threading.Lock()


def queue_for(key: str) -> RefreshQueue:
    with _queues_mu:
        queue = _queues.get(key)
        if queue is None:
            queue = RefreshQueue(cond=threading.Condition(), pending_paths=set())
            _queues[key] = queue
        return queue


def refresh_worker(
    roots: list[Path],
    queue: RefreshQueue,
    refresh_now: Callable[[list[Path]], ReadModelVersion],
    apply_now: Callable[[list[Path], list[Path]], ReadModelVersion],
    wait_for_write_queue_drain: Callable[[], None],
    publish_completed: Callable[..., None],
) -> None:
    while True:
        with queue.cond:
            while not queue.pending_full and not queue.pending_paths:
                queue.worker = None
                return
            delay = max(0.0, queue.next_due_monotonic - time.monotonic())
            if delay > 0:
                queue.cond.wait(timeout=delay)
                continue
            pending_full = queue.pending_full
            pending_paths = sorted(queue.pending_paths or [])
            queue.pending_full = False
            queue.pending_paths = set()
        wait_for_write_queue_drain()
        if pending_full:
            version = refresh_now(roots)
            publish_completed(roots, full_refresh=True, changed_paths=[], version=version)
            continue
        if pending_paths:
            version = apply_now(roots, pending_paths)
            publish_completed(roots, full_refresh=False, changed_paths=pending_paths, version=version)
