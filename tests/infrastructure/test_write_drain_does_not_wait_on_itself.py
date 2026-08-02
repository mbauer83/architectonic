"""A write that waits for the write queue to drain must not be waiting for itself.

The write queue has exactly one worker, so a job running on it is the only writer in the process. Any
code that job reaches which waits for the queue to become idle is therefore waiting on a count that
includes its own job — and that count cannot reach zero until the job returns. The job never returns.
Because the worker is single-threaded, every subsequent write on the process queues behind it for ever:
one call wedges the whole write surface of a running backend, with no error and no timeout.

`artifact_admin_reindex` did this. Its body calls `sync_refresh_for_roots`, whose first act is
`wait_for_write_queue_drain()` with no deadline, and it is registered in `MUTATION_TOOL_MANIFEST` — so
the MCP and REST executors both submit it to the queue before running it.

**Why nothing caught it.** `tests/tools/test_reindex_tool.py` covers both scopes, and covers them by
calling the tool *function*: the full-scope test monkeypatches `sync_refresh_for_roots` away, and the
entity-scope test takes a branch that never drains. Neither goes through the executor, so in both the
job count is zero and the wait returns at once. The defect lived entirely in the gap between calling a
tool and *submitting* it — which is the gap `tools/mcp/conformance.py --fixture` exists to close, and
it found this on its first run.

So the tests here assert the property at both layers: the primitive returns immediately for a caller on
the worker, and a real tool submitted the real way completes.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from src.infrastructure.artifact_index.coordination import (
    publish_write_queue_state,
    running_on_write_worker,
    wait_for_write_queue_drain,
)

#: Long enough that a machine under load does not fail this, short enough that a deadlock is reported
#: as one rather than as a hung suite. Never the subject of an assertion.
_TIMEOUT_S = 30.0


def _set_queue(*, active: int, pending: int) -> None:
    publish_write_queue_state(
        active_jobs=active, pending_jobs=pending, active_tool_name=None,
        active_operation_id=None, active_phase=None,
    )


@pytest.fixture(autouse=True)
def _idle_queue_afterwards():
    """The queue-state mirror is process-global, so a test that leaves it occupied hangs the next one."""
    yield
    _set_queue(active=0, pending=0)


class TestTheDrainPrimitive:
    def test_a_caller_on_the_write_worker_does_not_wait_for_the_queue_it_is_in(self) -> None:
        """The unit fix. With a job active, an unmarked caller must wait and a marked one must not."""
        _set_queue(active=1, pending=0)

        with running_on_write_worker():
            assert wait_for_write_queue_drain() is True

    def test_an_unmarked_caller_still_waits_and_still_gives_up_on_a_stalled_queue(self) -> None:
        """The half that must not be lost: the mark is the exemption, not a removal of the wait."""
        _set_queue(active=1, pending=0)

        assert wait_for_write_queue_drain(no_progress_s=0.2) is False

    def test_the_mark_is_restored_rather_than_cleared(self) -> None:
        """Nested submission must not leave the outer job unmarked when the inner one finishes."""
        with running_on_write_worker():
            with running_on_write_worker():
                pass
            _set_queue(active=1, pending=0)
            assert wait_for_write_queue_drain() is True

    def test_the_mark_does_not_leak_to_another_thread(self) -> None:
        """Thread-local, because the worker is one thread among many and the others must still wait."""
        _set_queue(active=1, pending=0)
        drained: list[bool] = []

        with running_on_write_worker():
            other = threading.Thread(
                target=lambda: drained.append(wait_for_write_queue_drain(no_progress_s=0.2))
            )
            other.start()
            other.join(timeout=_TIMEOUT_S)

        assert drained == [False]


class TestTheToolThatDeadlocked:
    def test_a_full_reindex_submitted_through_the_executor_completes(self, tmp_path: Path) -> None:
        """The regression, at the layer the defect was at: submitted, not called.

        Nothing is monkeypatched — `sync_refresh_for_roots` runs for real, which is the whole point.
        Before the fix this never returned; `asyncio.wait_for` turns that into a failure instead of a
        hung worker.
        """
        from src.infrastructure.mcp import mcp_artifact_server as server

        (tmp_path / "model").mkdir()
        handler = server.mcp_write._tool_manager._tools["artifact_admin_reindex"].fn

        async def _invoke() -> object:
            return await asyncio.wait_for(
                handler(scope="full", repo_root=str(tmp_path)), timeout=_TIMEOUT_S
            )

        result = asyncio.run(_invoke())

        assert isinstance(result, dict)
        assert result["status"] == "reindexed"

    def test_the_queue_is_usable_afterwards(self, tmp_path: Path) -> None:
        """The consequence that made this severe: a wedged worker takes every later write with it.

        Asserted separately, because a reindex that answered while leaving the worker occupied would
        satisfy the test above and still have broken the process.
        """
        from src.infrastructure.mcp import mcp_artifact_server as server
        from src.infrastructure.mcp.artifact_mcp.write_queue import submit_serialized

        (tmp_path / "model").mkdir()
        handler = server.mcp_write._tool_manager._tools["artifact_admin_reindex"].fn

        async def _invoke() -> object:
            return await asyncio.wait_for(
                handler(scope="full", repo_root=str(tmp_path)), timeout=_TIMEOUT_S
            )

        asyncio.run(_invoke())

        assert submit_serialized("probe", lambda: "ran").result(timeout=_TIMEOUT_S) == "ran"
