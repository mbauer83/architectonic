"""Tests for WorkspaceMutationGate — serialization, 423 surfaces, lock-order."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from src.infrastructure.rest.contracts.errors import ApiError, DenialDetails
from src.infrastructure.workspace.mutation_gate import (
    GateRejected,
    WorkspaceMutationGate,
    _reset_for_test,
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
    @pytest.mark.verifies("REQ@1782080517.IIl8-4")
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

    @pytest.mark.verifies("REQ@1782080517.IIl8-4")
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
    """Driven by a real index lock now, not by setting a flag the gate happened to read."""

    def test_gate_writing_raises_when_holding_index_write(self):
        from src.infrastructure.artifact_index._rwlock import _RWLock

        gate = WorkspaceMutationGate()
        with _RWLock().writing(), pytest.raises(AssertionError, match="Lock order violation"):
            with gate.writing():
                pass

    def test_gate_writing_ok_when_not_holding_index_write(self):
        gate = WorkspaceMutationGate()
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
        from src.infrastructure.mcp.artifact_mcp.write_queue import shutdown
        from src.infrastructure.rest.routers import state as gui_state
        from src.infrastructure.rest.routers.state import authorized_write
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
                with pytest.raises(ApiError) as exc_info:
                    authorized_write("entities_create_entity", lambda: None)
            return exc_info.value
        finally:
            gate.clear_block()
            _reset_executor_for_test()
            shutdown()
            del previous_engagement

    def test_a_sync_in_progress_is_refused_as_retryable_and_says_so(self, tmp_path: Path):
        # The reason as *data*: this asserted `"sync" in exc.detail` while the refusal was a bare
        # HTTPException, so a client had to match on English to tell a running sync from a read-only
        # workspace. Both now arrive as `DenialDetails`, whose docstring always said they should.
        exc = self._blocked_write(tmp_path, "sync_in_progress")
        assert exc.status_code == 423
        assert exc.code == "write_rejected"
        assert exc.details == DenialDetails(reason_code="sync_in_progress", retryable=True)

    def test_a_read_only_workspace_is_refused_as_retryable_and_says_so(self, tmp_path: Path):
        exc = self._blocked_write(tmp_path, "read_only")
        assert exc.status_code == 423
        assert exc.code == "write_rejected"
        assert exc.details == DenialDetails(reason_code="read_only", retryable=True)

    @pytest.mark.parametrize("reason", ["sync_in_progress", "read_only"])
    def test_the_status_and_the_retryable_flag_cannot_disagree(self, tmp_path: Path, reason: str):
        # They were decided in two places — a status chosen from a set of bare strings in the REST
        # layer, and a flag the error handler derived from that status. One vocabulary answers both.
        exc = self._blocked_write(tmp_path, reason)
        assert exc.details is not None
        assert exc.details.retryable is (exc.status_code == 423)


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


class TestAWaitingWriterIsReachable:
    """Overlapping readers used to make a writer unreachable, not merely slow.

    ``reading()`` waited only on ``_writing``, and its release notified only when ``_readers``
    reached zero. Under sustained overlapping reads the count never reached zero, so a waiting
    writer was never woken — the starvation was unbounded, and nothing in the structure could even
    express "a writer is waiting". ``_writers_waiting`` is that expression, and readers yield to it.
    """

    def test_a_writer_is_admitted_under_sustained_overlapping_reads(self) -> None:
        import threading
        import time

        from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

        gate = WorkspaceMutationGate()
        stop = threading.Event()
        admitted = threading.Event()

        def reader() -> None:
            while not stop.is_set():
                with gate.reading():
                    time.sleep(0.005)

        readers = [threading.Thread(target=reader, daemon=True) for _ in range(4)]
        for r in readers:
            r.start()
        time.sleep(0.05)

        def writer() -> None:
            with gate.writing():
                admitted.set()

        w = threading.Thread(target=writer, daemon=True)
        w.start()
        try:
            assert admitted.wait(timeout=5), "writer never woken under overlapping readers"
        finally:
            stop.set()
            for r in readers:
                r.join(timeout=2)
            w.join(timeout=2)

    def test_a_reader_arriving_behind_a_waiting_writer_waits(self) -> None:
        """The other half: yielding must actually order the reader behind the writer."""
        import threading
        import time

        from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

        gate = WorkspaceMutationGate()
        order: list[str] = []
        lock = threading.Lock()
        first_reader_in = threading.Event()
        release_first = threading.Event()

        def first_reader() -> None:
            with gate.reading():
                first_reader_in.set()
                release_first.wait(timeout=5)

        def writer() -> None:
            with gate.writing():
                with lock:
                    order.append("writer")

        def late_reader() -> None:
            with gate.reading():
                with lock:
                    order.append("reader")

        t1 = threading.Thread(target=first_reader, daemon=True)
        t1.start()
        assert first_reader_in.wait(timeout=5)
        tw = threading.Thread(target=writer, daemon=True)
        tw.start()
        time.sleep(0.05)  # let the writer register as waiting
        tr = threading.Thread(target=late_reader, daemon=True)
        tr.start()
        time.sleep(0.05)
        release_first.set()

        for t in (t1, tw, tr):
            t.join(timeout=5)
        assert order == ["writer", "reader"], order


class TestLockOwnershipIsAskedOfTheLock:
    """The order detector reads the index locks, not a mirror of them.

    A thread-local flag was a second copy of state the lock already owned. It failed in two ways a
    single source cannot: a missed clear left a pooled worker raising spurious violations on every
    later unrelated task, and a lock acquired on one thread while the gate was requested on another
    read a clean flag and let a genuine inversion through undetected.
    """

    def test_same_thread_inversion_is_still_detected(self) -> None:
        import pytest

        from src.infrastructure.artifact_index._rwlock import _RWLock
        from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

        lock, gate = _RWLock(), WorkspaceMutationGate()
        with lock.writing(), pytest.raises(AssertionError, match="Lock order violation"):
            with gate.writing():
                pass

    def test_the_read_path_is_guarded_too(self) -> None:
        """Verification takes READ, so the inversion matters there as much as on a write."""
        import pytest

        from src.infrastructure.artifact_index._rwlock import _RWLock
        from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

        lock, gate = _RWLock(), WorkspaceMutationGate()
        with lock.writing(), pytest.raises(AssertionError, match="Lock order violation"):
            with gate.reading():
                pass

    def test_the_privileged_write_path_is_guarded_too(self) -> None:
        import pytest

        from src.infrastructure.artifact_index._rwlock import _RWLock
        from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

        lock, gate = _RWLock(), WorkspaceMutationGate()
        with lock.writing(), pytest.raises(AssertionError, match="Lock order violation"):
            with gate.privileged_writing():
                pass

    def test_a_lock_held_by_another_thread_is_not_this_thread_s_violation(self) -> None:
        """The mirror could not tell these apart; ownership by thread ident can."""
        import threading

        from src.infrastructure.artifact_index._rwlock import _RWLock
        from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

        lock, gate = _RWLock(), WorkspaceMutationGate()
        held, release = threading.Event(), threading.Event()

        def holder() -> None:
            with lock.writing():
                held.set()
                release.wait(timeout=5)

        t = threading.Thread(target=holder, daemon=True)
        t.start()
        assert held.wait(timeout=5)
        try:
            with gate.reading():  # another thread holds the index lock — not our inversion
                pass
        finally:
            release.set()
            t.join(timeout=5)

    def test_releasing_the_index_lock_clears_ownership(self) -> None:
        from src.infrastructure.artifact_index._rwlock import (
            _RWLock,
            current_thread_holds_index_write,
        )

        lock = _RWLock()
        with lock.writing():
            assert current_thread_holds_index_write()
        assert not current_thread_holds_index_write()

    def test_no_thread_local_mirror_remains(self) -> None:
        """Asserted structurally: the defect class is gone, not merely unused."""
        from src.infrastructure.workspace import mutation_gate

        assert not hasattr(mutation_gate, "_tl")
        assert not hasattr(mutation_gate, "_mark_index_write_held")
