"""Tests for the model write queue serialization mechanism.

Verifies that:
- submit_serialized schedules work on the single write worker and returns a Future
- concurrent writes are serialized (no interleaving) and FIFO-ordered
- results and exceptions propagate to each caller without wedging the queue
- queue-state publication carries active operation metadata
- shutdown resets cleanly and a new executor is created on the next call
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from typing import Any

import pytest

from src.infrastructure.mcp.artifact_mcp.write_queue import shutdown, submit_serialized
from src.infrastructure.write.operation_registry import operation_registry


@pytest.fixture(autouse=True)
def reset_executor():
    """Ensure a fresh executor for each test."""
    shutdown(wait=True)
    yield
    shutdown(wait=True)


class TestSubmitSerialized:
    def test_returns_future_with_result(self):
        def sync_fn(x: int, y: int) -> int:
            return x + y

        future = submit_serialized("sync_fn", sync_fn, 3, 4)
        assert isinstance(future, Future)
        assert future.result(timeout=10) == 7

    def test_kwargs_forwarded(self):
        def sync_fn(*, name: str, count: int = 1) -> list[str]:
            return [name] * count

        assert submit_serialized("sync_fn", sync_fn, name="hello", count=3).result(timeout=10) == [
            "hello",
            "hello",
            "hello",
        ]

    def test_exception_propagates(self):
        def sync_fn() -> None:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            submit_serialized("sync_fn", sync_fn).result(timeout=10)


class TestSerialization:
    def test_concurrent_submissions_are_serialized(self):
        """At most one queued write should run at a time."""
        active: list[int] = []
        peak_concurrency: list[int] = []
        lock = threading.Lock()

        def slow_write(task_id: int) -> int:
            with lock:
                active.append(task_id)
                peak_concurrency.append(len(active))
            time.sleep(0.01)
            with lock:
                active.remove(task_id)
            return task_id

        futures = [submit_serialized("slow_write", slow_write, i) for i in range(8)]
        results = [future.result(timeout=10) for future in futures]
        assert sorted(results) == list(range(8))
        assert max(peak_concurrency) == 1, f"Expected max concurrency of 1, got {max(peak_concurrency)}"

    def test_ordering_is_fifo(self):
        """Work executes in submission order (FIFO queue)."""
        execution_order: list[int] = []

        def ordered_write(task_id: int) -> int:
            execution_order.append(task_id)
            return task_id

        futures = [submit_serialized("ordered_write", ordered_write, i) for i in range(5)]
        assert [future.result(timeout=10) for future in futures] == list(range(5))
        assert execution_order == list(range(5))

    def test_exception_does_not_block_subsequent_writes(self):
        """A write that raises should not leave the queue stuck."""
        call_count: list[int] = [0]

        def maybe_raise(fail: bool) -> str:
            call_count[0] += 1
            if fail:
                raise RuntimeError("intentional failure")
            return "ok"

        with pytest.raises(RuntimeError):
            submit_serialized("maybe_raise", maybe_raise, fail=True).result(timeout=10)
        assert submit_serialized("maybe_raise", maybe_raise, fail=False).result(timeout=10) == "ok"
        assert call_count[0] == 2

    def test_multiple_concurrent_exceptions_do_not_block(self):
        """Multiple concurrent failures should each propagate without deadlock."""

        def always_fail(task_id: int) -> None:
            raise ValueError(f"fail-{task_id}")

        futures = [submit_serialized("always_fail", always_fail, i) for i in range(4)]
        for i, future in enumerate(futures):
            with pytest.raises(ValueError, match=f"fail-{i}"):
                future.result(timeout=10)

    def test_queue_state_includes_active_operation_metadata(self, monkeypatch: pytest.MonkeyPatch):
        published: list[dict[str, Any]] = []

        def capture_state(**kwargs: Any) -> None:
            published.append(dict(kwargs))

        monkeypatch.setattr(
            "src.infrastructure.mcp.artifact_mcp.write_queue.publish_write_queue_state",
            capture_state,
        )

        def tracked_write() -> str:
            operation, reused = operation_registry.begin(
                tool_name="artifact_bulk_write",
                idempotency_key=None,
            )
            assert reused is None
            operation_registry.set_phase(operation.operation_id, "apply")
            time.sleep(0.01)
            operation_registry.complete(operation.operation_id, {"ok": True})
            return operation.operation_id

        operation_id = submit_serialized("tracked_write", tracked_write).result(timeout=10)

        active_snapshots = [snapshot for snapshot in published if snapshot.get("active_operation_id") == operation_id]
        assert active_snapshots, published
        assert any(snapshot.get("active_tool_name") == "tracked_write" for snapshot in active_snapshots)
        assert any(snapshot.get("active_phase") == "apply" for snapshot in active_snapshots)
        assert published[-1]["active_jobs"] == 0
        assert published[-1]["pending_jobs"] == 0
        assert published[-1]["active_operation_id"] is None


class TestShutdown:
    def test_shutdown_and_restart(self):
        """After shutdown, a new executor is created on the next call."""

        def sync_fn() -> str:
            return "alive"

        assert submit_serialized("sync_fn", sync_fn).result(timeout=10) == "alive"
        shutdown(wait=True)
        assert submit_serialized("sync_fn", sync_fn).result(timeout=10) == "alive"
