"""Tests for operation_registry.py — subscribe/unsubscribe, fail, set_phase edge cases."""

from __future__ import annotations

from src.infrastructure.write.operation_registry import OperationRegistry


class TestOperationRegistrySubscribe:
    def test_subscribe_and_unsubscribe(self) -> None:
        reg = OperationRegistry()
        received: list[dict] = []
        unsubscribe = reg.subscribe(received.append)
        record, _ = reg.begin(tool_name="test_tool", idempotency_key=None)
        assert len(received) == 1
        unsubscribe()
        reg.complete(record.operation_id, result="done")
        # After unsubscribe, no new notifications
        assert len(received) == 1

    def test_unsubscribe_removes_listener_from_list(self) -> None:
        reg = OperationRegistry()
        calls: list[dict] = []
        unsubscribe = reg.subscribe(calls.append)
        unsubscribe()
        unsubscribe()  # double-unsubscribe is safe
        record, _ = reg.begin(tool_name="t", idempotency_key=None)
        assert not calls  # no notifications after unsubscribe


class TestOperationRegistryFail:
    def test_fail_sets_status_and_error(self) -> None:
        reg = OperationRegistry()
        snapshots: list[dict] = []
        reg.subscribe(snapshots.append)
        record, _ = reg.begin(tool_name="failing_tool", idempotency_key=None)
        reg.fail(record.operation_id, error="something went wrong")
        last = reg.get(record.operation_id)
        assert last is not None
        assert last["status"] == "failed"
        assert last["error"] == "something went wrong"
        assert last["phase"] == "done"


class TestSetPhaseEdgeCases:
    def test_set_phase_unknown_id_is_silent(self) -> None:
        reg = OperationRegistry()
        calls: list[dict] = []
        reg.subscribe(calls.append)
        before = len(calls)
        reg.set_phase("op_nonexistent", "some_phase")
        # Should not notify for unknown operation
        assert len(calls) == before

    def test_set_phase_known_id_notifies(self) -> None:
        reg = OperationRegistry()
        calls: list[dict] = []
        reg.subscribe(calls.append)
        record, _ = reg.begin(tool_name="phased_tool", idempotency_key=None)
        before = len(calls)
        reg.set_phase(record.operation_id, "execute")
        assert len(calls) > before


class TestIdempotencyKey:
    def test_idempotency_returns_cached_result(self) -> None:
        reg = OperationRegistry()
        record1, _ = reg.begin(tool_name="tool", idempotency_key="key-1")
        reg.complete(record1.operation_id, result="result-1")
        record2, cached = reg.begin(tool_name="tool", idempotency_key="key-1")
        assert cached == "result-1"
        assert record2.operation_id == record1.operation_id
