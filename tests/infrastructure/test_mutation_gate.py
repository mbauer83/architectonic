"""Tests for WorkspaceMutationGate — serialization, 423 surfaces, lock-order."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from src.infrastructure.workspace.mutation_gate import (
    GateRejected,
    WorkspaceMutationGate,
    _mark_index_write_held,
    _reset_for_test,
    _tl,
)


@pytest.fixture(autouse=True)
def fresh_gate():
    """Each test gets clean gate and write-executor singletons."""
    from src.infrastructure.mcp.artifact_mcp.write_queue import shutdown

    shutdown()
    _reset_for_test()
    yield
    shutdown()
    _reset_for_test()


# ---------------------------------------------------------------------------
# Gate unit tests
# ---------------------------------------------------------------------------

class TestGateWriting:
    def test_write_excludes_concurrent_write(self):
        gate = WorkspaceMutationGate()
        order: list[str] = []
        barrier = threading.Barrier(2)

        def writer_a():
            with gate.writing():
                barrier.wait()
                order.append("a-in")
                threading.Event().wait(0.05)
                order.append("a-out")

        def writer_b():
            barrier.wait()
            with gate.writing():
                order.append("b-in")

        t_a = threading.Thread(target=writer_a)
        t_b = threading.Thread(target=writer_b)
        t_a.start()
        t_b.start()
        t_a.join(timeout=2)
        t_b.join(timeout=2)

        assert order == ["a-in", "a-out", "b-in"], f"Unexpected order: {order}"

    def test_write_excludes_concurrent_read(self):
        gate = WorkspaceMutationGate()
        events: list[str] = []
        write_started = threading.Event()

        def writer():
            with gate.writing():
                write_started.set()
                threading.Event().wait(0.05)
                events.append("write-done")

        def reader():
            write_started.wait()
            with gate.reading():
                events.append("read-in")

        t_w = threading.Thread(target=writer)
        t_r = threading.Thread(target=reader)
        t_w.start()
        t_r.start()
        t_w.join(timeout=2)
        t_r.join(timeout=2)

        assert events == ["write-done", "read-in"]

    def test_multiple_reads_concurrent(self):
        gate = WorkspaceMutationGate()
        inside: list[int] = []
        barrier = threading.Barrier(3)

        def reader(n: int):
            with gate.reading():
                barrier.wait()
                inside.append(n)

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)

        assert sorted(inside) == [0, 1, 2]

    def test_write_raises_when_sync_in_progress(self):
        gate = WorkspaceMutationGate()
        gate.set_block("sync_in_progress")
        with pytest.raises(GateRejected) as exc_info:
            with gate.writing():
                pass
        assert exc_info.value.reason == "sync_in_progress"

    def test_write_raises_when_read_only(self):
        gate = WorkspaceMutationGate()
        gate.set_block("read_only")
        with pytest.raises(GateRejected) as exc_info:
            with gate.writing():
                pass
        assert exc_info.value.reason == "read_only"

    def test_clear_block_restores_writing(self):
        gate = WorkspaceMutationGate()
        gate.set_block("sync_in_progress")
        gate.clear_block()
        executed = []
        with gate.writing():
            executed.append(True)
        assert executed == [True]


class TestBlockingWrites:
    def test_blocking_writes_context_blocks_then_releases(self):
        gate = WorkspaceMutationGate()
        executed: list[str] = []

        with gate.blocking_writes("sync_in_progress"):
            assert gate.block_reason == "sync_in_progress"
            with pytest.raises(GateRejected):
                with gate.writing():
                    pass

        assert gate.block_reason is None
        with gate.writing():
            executed.append("ok")
        assert executed == ["ok"]

    def test_blocking_writes_flushes_active_writer(self):
        gate = WorkspaceMutationGate()
        write_held = threading.Event()
        block_entered = threading.Event()
        results: list[str] = []

        def writer():
            with gate.writing():
                write_held.set()
                block_entered.wait(timeout=1)
                results.append("write-finished")

        def blocker():
            write_held.wait(timeout=1)
            # blocking_writes must wait for the active writer to finish
            with gate.blocking_writes("sync_in_progress"):
                block_entered.set()
                results.append("block-active")

        t_w = threading.Thread(target=writer)
        t_b = threading.Thread(target=blocker)
        t_w.start()
        t_b.start()
        t_w.join(timeout=2)
        t_b.join(timeout=2)

        assert results[0] == "write-finished"
        assert results[1] == "block-active"


class TestPrivilegedWriting:
    def test_privileged_writing_bypasses_block(self):
        gate = WorkspaceMutationGate()
        results: list[str] = []

        gate.set_block("sync_in_progress")
        with gate.privileged_writing():
            results.append("privileged")
        assert results == ["privileged"]

    def test_block_reason_still_active_during_privileged_write(self):
        gate = WorkspaceMutationGate()
        held = threading.Event()
        rejected: list[GateRejected] = []

        def privileged():
            with gate.privileged_writing():
                held.set()
                threading.Event().wait(0.05)

        gate.set_block("sync_in_progress")

        t = threading.Thread(target=privileged)
        t.start()
        held.wait(timeout=1)

        try:
            with gate.writing():
                pass
        except GateRejected as exc:
            rejected.append(exc)

        t.join(timeout=2)

        assert len(rejected) == 1
        assert rejected[0].reason == "sync_in_progress"


# ---------------------------------------------------------------------------
# Lock-order assertion
# ---------------------------------------------------------------------------

class TestLockOrder:
    def test_gate_writing_raises_when_holding_index_write(self):
        gate = WorkspaceMutationGate()
        _tl.holding_index_write = False

        _mark_index_write_held(True)
        try:
            with pytest.raises(AssertionError, match="Lock order violation"):
                with gate.writing():
                    pass
        finally:
            _mark_index_write_held(False)

    def test_gate_writing_ok_when_not_holding_index_write(self):
        gate = WorkspaceMutationGate()
        _tl.holding_index_write = False
        executed = []
        with gate.writing():
            executed.append(True)
        assert executed == [True]


# ---------------------------------------------------------------------------
# HTTP surface (state.authorized_write → HTTPException 423)
# ---------------------------------------------------------------------------

class TestHttpSurface:
    """REST writes fail closed with HTTP 423 while the workspace gate is blocked."""

    def _blocked_write(self, tmp_path: Path, reason):
        from fastapi import HTTPException

        from src.infrastructure.gui.routers import state as gui_state
        from src.infrastructure.gui.routers.state import authorized_write
        from src.infrastructure.mcp.artifact_mcp.write_queue import shutdown
        from src.infrastructure.workspace.mutation_gate import get_workspace_gate as _gwg
        from src.infrastructure.write.authorized_mutation_executor import build_workspace_mutation_executor
        from src.infrastructure.write.mutation_executor_registry import (
            _reset_executor_for_test,
            install_mutation_executor,
        )
        from src.infrastructure.write.workspace_authorization import WorkspaceAuthorizationSnapshots

        engagement = tmp_path / "engagements" / "ENG-HTTP" / "architecture-repository"
        engagement.mkdir(parents=True)
        previous_engagement = gui_state.maybe_engagement_root()
        gate = _gwg()
        install_mutation_executor(
            build_workspace_mutation_executor(
                WorkspaceAuthorizationSnapshots(
                    engagement_root=engagement,
                    enterprise_root=None,
                    admin_mode=False,
                    read_only=False,
                    gate=gate,
                )
            )
        )
        gate.set_block(reason)
        try:
            import unittest.mock

            with unittest.mock.patch.object(gui_state, "maybe_engagement_root", lambda: engagement):
                with pytest.raises(HTTPException) as exc_info:
                    authorized_write(("POST", "/api/entity"), lambda: None)
            return exc_info.value
        finally:
            gate.clear_block()
            _reset_executor_for_test()
            shutdown()
            del previous_engagement

    def test_authorized_write_returns_423_on_sync_blocked(self, tmp_path: Path):
        exc = self._blocked_write(tmp_path, "sync_in_progress")
        assert exc.status_code == 423
        assert "sync" in exc.detail

    def test_authorized_write_returns_423_on_read_only(self, tmp_path: Path):
        exc = self._blocked_write(tmp_path, "read_only")
        assert exc.status_code == 423
        assert "read-only" in exc.detail


# ---------------------------------------------------------------------------
# write_block_manager shim
# ---------------------------------------------------------------------------

class TestWriteBlockManagerShim:
    def test_block_and_is_blocked(self):
        from src.infrastructure.workspace.write_block_manager import block_repo, is_blocked, unblock_repo

        root = Path("/fake/root")
        assert not is_blocked(root)
        block_repo(root)
        assert is_blocked(root)
        unblock_repo(root)
        assert not is_blocked(root)

    def test_block_reason_passed_to_gate(self):
        from src.infrastructure.workspace.mutation_gate import get_workspace_gate as _gwg
        from src.infrastructure.workspace.write_block_manager import block_repo, unblock_repo

        root = Path("/fake/root")
        block_repo(root, reason="read_only")
        assert _gwg().block_reason == "read_only"

        # unblock_repo must NOT clear read_only — it is a permanent mode
        unblock_repo(root)
        assert _gwg().block_reason == "read_only", (
            "unblock_repo must not clear a read_only block"
        )

    def test_sync_block_does_not_override_read_only(self):
        from src.infrastructure.workspace.mutation_gate import get_workspace_gate as _gwg
        from src.infrastructure.workspace.write_block_manager import block_repo, unblock_repo

        root = Path("/fake/root")
        block_repo(root, reason="read_only")

        # A subsequent sync must not downgrade to sync_in_progress
        block_repo(root)  # default reason = sync_in_progress
        assert _gwg().block_reason == "read_only", (
            "sync block must not overwrite read_only"
        )

        unblock_repo(root)  # still must not clear it
        assert _gwg().block_reason == "read_only"


def test_write_executor_rejects_multiple_workers(monkeypatch) -> None:
    from src.infrastructure.mcp.artifact_mcp import write_queue

    write_queue.shutdown()
    monkeypatch.setattr(write_queue, "_WRITE_EXECUTOR_WORKERS", 2)

    with pytest.raises(AssertionError, match="single-worker"):
        write_queue._get_executor()
