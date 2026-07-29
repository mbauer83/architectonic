from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

OperationStatus = Literal["running", "completed", "failed"]


@dataclass
class OperationRecord:
    operation_id: str
    tool_name: str
    idempotency_key: str | None
    status: OperationStatus
    phase: str
    enqueued_at: float
    started_at: float | None = None
    ended_at: float | None = None
    result: Any = None
    error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "tool_name": self.tool_name,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "phase": self.phase,
            "enqueued_at": self.enqueued_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
            "result": self.result,
        }


class OperationRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_operation_id: dict[str, OperationRecord] = {}
        self._completed_by_key: dict[tuple[str, str], str] = {}
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    def subscribe(self, listener: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def _notify(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener(snapshot)

    def begin(self, *, tool_name: str, idempotency_key: str | None) -> tuple[OperationRecord, Any | None]:
        with self._lock:
            if idempotency_key:
                existing_id = self._completed_by_key.get((tool_name, idempotency_key))
                if existing_id is not None:
                    existing = self._by_operation_id[existing_id]
                    return existing, existing.result

            now = time.time()
            record = OperationRecord(
                operation_id=f"op_{uuid.uuid4().hex}",
                tool_name=tool_name,
                idempotency_key=idempotency_key,
                status="running",
                phase="preflight",
                enqueued_at=now,
                started_at=now,
            )
            self._by_operation_id[record.operation_id] = record
            snapshot = record.snapshot()
        self._notify(snapshot)
        return record, None

    def set_phase(self, operation_id: str, phase: str) -> None:
        with self._lock:
            record = self._by_operation_id.get(operation_id)
            if record is not None:
                record.phase = phase
                snapshot = record.snapshot()
            else:
                snapshot = None
        if snapshot is not None:
            self._notify(snapshot)

    def complete(self, operation_id: str, result: Any) -> None:
        with self._lock:
            record = self._by_operation_id[operation_id]
            record.status = "completed"
            record.phase = "done"
            record.ended_at = time.time()
            record.result = result
            if record.idempotency_key:
                self._completed_by_key[(record.tool_name, record.idempotency_key)] = operation_id
            snapshot = record.snapshot()
        self._notify(snapshot)

    def fail(self, operation_id: str, error: str) -> None:
        with self._lock:
            record = self._by_operation_id[operation_id]
            record.status = "failed"
            record.phase = "done"
            record.ended_at = time.time()
            record.error = error
            snapshot = record.snapshot()
        self._notify(snapshot)

    def get(self, operation_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._by_operation_id.get(operation_id)
            return None if record is None else record.snapshot()


operation_registry = OperationRegistry()
