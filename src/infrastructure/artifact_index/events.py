"""Typed events for model-index lifecycle coordination.

These events are intentionally small and process-local. They decouple the
authoritative write path from background reconciliation without introducing a
heavier dependency or queueing system.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from .versioning import ReadModelVersion


@dataclass(frozen=True)
class WriteQueueStateChanged:
    """Snapshot of the serialized write queue state."""

    active_jobs: int
    pending_jobs: int
    active_tool_name: str | None = None
    active_operation_id: str | None = None
    active_phase: str | None = None


@dataclass(frozen=True)
class AuthoritativeIndexMutationCommitted:
    """A first-party write committed paths directly into the authoritative index."""

    roots_key: str
    changed_paths: tuple[str, ...]
    version: ReadModelVersion


@dataclass(frozen=True)
class BackgroundIndexRefreshCompleted:
    """A watcher- or interval-driven reconciliation refresh completed."""

    roots_key: str
    full_refresh: bool
    changed_paths: tuple[str, ...]
    version: ReadModelVersion


_EventT = TypeVar("_EventT")


class IndexEventBus:
    """Minimal synchronous in-process event bus."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[type[object], list[Callable[[object], None]]] = {}

    def subscribe(self, event_type: type[_EventT], handler: Callable[[_EventT], None]) -> Callable[[], None]:
        with self._lock:
            handlers = self._subscribers.setdefault(event_type, [])
            handlers.append(handler)  # type: ignore[arg-type]

        def unsubscribe() -> None:
            with self._lock:
                registered = self._subscribers.get(event_type, [])
                if handler in registered:
                    registered.remove(handler)  # type: ignore[arg-type]

        return unsubscribe

    def publish(self, event: object) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(type(event), ()))
        for handler in handlers:
            handler(event)


event_bus = IndexEventBus()
