"""Unit tests for the shared SingleWriterQueue primitive."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from src.infrastructure.concurrency.single_writer_queue import SingleWriterQueue


def test_runs_serially_max_in_flight_one() -> None:
    q = SingleWriterQueue("test-queue")
    try:
        observed_concurrent = []
        counter = {"active": 0}
        lock = threading.Lock()

        def _job() -> None:
            with lock:
                counter["active"] += 1
                observed_concurrent.append(counter["active"])
            time.sleep(0.01)
            with lock:
                counter["active"] -= 1

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(q.run_sync, _job) for _ in range(20)]
            for f in futures:
                f.result()

        assert max(observed_concurrent) == 1
        assert q.max_observed_in_flight == 1
    finally:
        q.shutdown()


def test_concurrent_first_submits_build_only_one_executor(monkeypatch) -> None:
    """Regression: concurrent first-time submits must build exactly one single-worker
    executor. Lazy init was a check-then-act race — two callers could each see ``None``
    and each build their own executor, yielding two live writers (the bug that made
    ``max_observed_in_flight`` intermittently reach 2 under parallel load).

    The window between the ``None`` check and the assignment is normally sub-microsecond,
    so we widen it deterministically: a slow executor constructor guarantees every aligned
    thread passes the check before the first assignment lands. With the fix the lock
    serialises them and only one executor is ever constructed; without it, one per thread.
    """
    import src.infrastructure.concurrency.single_writer_queue as swq_module

    real_ctor = swq_module.ThreadPoolExecutor
    constructed: list[object] = []
    n = 8
    aligned = threading.Barrier(n)

    def _slow_ctor(*args: object, **kwargs: object) -> object:
        time.sleep(0.05)  # hold the check→assign window open across all callers
        executor = real_ctor(*args, **kwargs)  # type: ignore[arg-type]
        constructed.append(executor)
        return executor

    monkeypatch.setattr(swq_module, "ThreadPoolExecutor", _slow_ctor)

    q = SingleWriterQueue("test-queue")
    try:
        def _worker() -> None:
            aligned.wait()
            q.run_sync(lambda: None)

        threads = [threading.Thread(target=_worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(constructed) == 1
        assert q.max_observed_in_flight == 1
    finally:
        q.shutdown()


def test_run_sync_returns_result_and_propagates_errors() -> None:
    q = SingleWriterQueue("test-queue")
    try:
        assert q.run_sync(lambda x: x + 1, 41) == 42

        def _boom() -> None:
            raise ValueError("boom")

        try:
            q.run_sync(_boom)
        except ValueError as exc:
            assert str(exc) == "boom"
        else:  # pragma: no cover
            raise AssertionError("expected ValueError")
    finally:
        q.shutdown()


def test_wait_until_idle_and_shutdown() -> None:
    q = SingleWriterQueue("test-queue")
    results: list[int] = []
    for i in range(5):
        q.submit(lambda n: results.append(n), i)
    assert q.wait_until_idle(timeout_s=5.0)
    assert sorted(results) == [0, 1, 2, 3, 4]
    assert q.pending() == 0
    q.shutdown()
