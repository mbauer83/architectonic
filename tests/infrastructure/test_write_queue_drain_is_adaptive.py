"""The write drain waits on progress, not on the clock.

An absolute "wait N seconds for writes" encodes the disk speed, machine load and commit size of
whoever picked N. It is wrong on a slower disk, on a busier box, and on a bulk write an order of
magnitude larger than the one it was tuned against — and where the wait protects something, being
wrong means proceeding while the thing is still in flight.

So the property under test is not a duration. It is: *a queue that is still completing work is waited
on however long that takes; a queue that has stopped moving is not waited on however recently it
started.* Both halves are asserted, because either alone is satisfied by a bug — an unconditional wait
passes the first, and an unconditional give-up passes the second.

Driven by the queue's own state publisher rather than by sleeping, so the tests say nothing about how
fast this machine is either.
"""

from __future__ import annotations

import threading
import time

from src.infrastructure.artifact_index.coordination import (
    publish_write_queue_state,
    wait_for_write_queue_drain,
)

#: Short enough to keep the suite quick, and never the subject of an assertion.
_STALL_PATIENCE = 0.3


def _set_queue(*, active: int, pending: int, operation_id: str | None = None) -> None:
    publish_write_queue_state(
        active_jobs=active, pending_jobs=pending, active_tool_name=None,
        active_operation_id=operation_id, active_phase=None,
    )


def _idle_queue() -> None:
    _set_queue(active=0, pending=0)


class TestProgressEarnsPatience:
    def test_a_queue_that_keeps_completing_work_is_waited_on_past_the_stall_patience(self) -> None:
        """The half an absolute timeout gets wrong. Six steps of work, each arriving just inside the
        stall patience, take longer in total than that patience — and must still be waited for."""
        _set_queue(active=1, pending=5)
        try:
            def make_progress() -> None:
                for remaining in (4, 3, 2, 1, 0):
                    time.sleep(_STALL_PATIENCE / 2)
                    _set_queue(active=1, pending=remaining)
                time.sleep(_STALL_PATIENCE / 2)
                _idle_queue()

            worker = threading.Thread(target=make_progress)
            started = time.monotonic()
            worker.start()
            drained = wait_for_write_queue_drain(timeout_s=30, no_progress_s=_STALL_PATIENCE)
            worker.join()

            assert drained is True, "a queue making progress must not be abandoned"
            assert time.monotonic() - started > _STALL_PATIENCE, (
                "the wait ended before the patience elapsed, so this proved nothing"
            )
        finally:
            _idle_queue()

    def test_a_changed_operation_counts_as_progress_even_at_the_same_depth(self) -> None:
        """Queue depth alone is not progress: one job finishing as another starts leaves the counts
        identical. The active operation id is what distinguishes work from a stall."""
        _set_queue(active=1, pending=0, operation_id="first")
        try:
            def hand_over() -> None:
                time.sleep(_STALL_PATIENCE / 2)
                _set_queue(active=1, pending=0, operation_id="second")
                time.sleep(_STALL_PATIENCE / 2)
                _idle_queue()

            worker = threading.Thread(target=hand_over)
            worker.start()
            drained = wait_for_write_queue_drain(timeout_s=30, no_progress_s=_STALL_PATIENCE)
            worker.join()
            assert drained is True
        finally:
            _idle_queue()


class TestStallingEndsTheWait:
    def test_a_queue_that_stops_moving_is_given_up_on(self) -> None:
        """The other half. Without this the drain would hang a shutdown that something else will
        then SIGKILL — which is the ending the whole contract exists to avoid."""
        _set_queue(active=1, pending=3)
        try:
            assert wait_for_write_queue_drain(timeout_s=30, no_progress_s=_STALL_PATIENCE) is False
        finally:
            _idle_queue()

    def test_the_ceiling_still_applies_to_a_queue_that_never_finishes(self) -> None:
        """Progress alone must not buy unbounded patience: the process may not outlive the deadline
        its stopper will kill it at, however busy it is."""
        _set_queue(active=1, pending=1)
        try:
            def churn(stop: threading.Event) -> None:
                depth = 1
                while not stop.is_set():
                    depth = 2 if depth == 1 else 1
                    _set_queue(active=1, pending=depth)
                    time.sleep(_STALL_PATIENCE / 4)

            stop = threading.Event()
            worker = threading.Thread(target=churn, args=(stop,))
            worker.start()
            try:
                drained = wait_for_write_queue_drain(
                    timeout_s=_STALL_PATIENCE * 3, no_progress_s=_STALL_PATIENCE,
                )
            finally:
                stop.set()
                worker.join()
            assert drained is False, "endless progress must still hit the ceiling"
        finally:
            _idle_queue()


def test_an_idle_queue_returns_at_once_whatever_the_bounds_say() -> None:
    """The common case at shutdown, and the reason the ceiling being generous costs nothing."""
    _idle_queue()
    started = time.monotonic()
    assert wait_for_write_queue_drain(timeout_s=30, no_progress_s=_STALL_PATIENCE) is True
    assert time.monotonic() - started < _STALL_PATIENCE
