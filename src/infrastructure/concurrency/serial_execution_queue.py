"""Serial execution queue — one worker, running submitted work one at a time.

The mechanism: a single-worker ``ThreadPoolExecutor`` accepts every call immediately and returns
each result as soon as it completes, but only **one** runs at a time. It also takes work *off* the
caller's thread, which is what an async caller needs from it — the event loop must not be occupied
by work measured in seconds.

Named for what it does rather than for the first domain that needed it. Two of them serialise
writes, because concurrent writes race on shared state (model `.md` files plus the arch SQLite
index; the assurance SQLCipher DB's audit-log ``seq``); a third runs verification passes, which
race on nothing and use it for the dedicated worker and the lifecycle. Each domain holds its own
instance, so none falsely serialises against another.

Usage::

    queue = SerialExecutionQueue("assurance-write-queue")
    result = queue.run_sync(write_fn, *args, **kwargs)        # REST handlers
    result = await queue.submit_async(write_fn, *args, **kwargs)  # async callers

The arch model-write-queue keeps its own GUI/operation-registry hooks layered on
top of the same shape; this primitive provides the executor + in-flight accounting
that any serialised domain needs.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")


class SerialExecutionQueue:
    """A serialised, single-worker execution queue with in-flight accounting."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Condition()
        self._submitted = 0
        self._completed = 0
        self._active = 0
        self._max_observed_in_flight = 0

    # ── Executor lifecycle ─────────────────────────────────────────────────────

    def _get_executor(self) -> ThreadPoolExecutor:
        # Double-checked locking: the lazy (re)creation must be atomic, or concurrent
        # first-time submits each see ``None`` and each build a *separate* single-worker
        # executor — two live workers then run writes concurrently, defeating the whole
        # serialisation guarantee. The unlocked fast path keeps the hot path lock-free.
        executor = self._executor
        if executor is not None and not executor._shutdown:  # noqa: SLF001
            return executor
        with self._lock:
            if self._executor is None or self._executor._shutdown:  # noqa: SLF001
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=self._name)
            return self._executor

    # ── Submission ─────────────────────────────────────────────────────────────

    def _run_job(self, fn: Callable[..., _T], /, *args: Any, **kwargs: Any) -> _T:
        with self._lock:
            self._active += 1
            self._max_observed_in_flight = max(self._max_observed_in_flight, self._active)
        try:
            return fn(*args, **kwargs)
        finally:
            with self._lock:
                self._active -= 1
                self._completed += 1
                self._lock.notify_all()

    def submit(self, fn: Callable[..., _T], /, *args: Any, **kwargs: Any) -> Future[_T]:
        """Schedule *fn* on the single worker; returns its Future."""
        with self._lock:
            self._submitted += 1
        return self._get_executor().submit(self._run_job, fn, *args, **kwargs)

    def run_sync(self, fn: Callable[..., _T], /, *args: Any, **kwargs: Any) -> _T:
        """Submit and block for the result (for synchronous REST handlers)."""
        return self.submit(fn, *args, **kwargs).result()

    async def submit_async(self, fn: Callable[..., _T], /, *args: Any, **kwargs: Any) -> _T:
        """Submit and await the result without blocking the event loop."""
        return await asyncio.wrap_future(self.submit(fn, *args, **kwargs))

    # ── Introspection / teardown ───────────────────────────────────────────────

    @property
    def max_observed_in_flight(self) -> int:
        """Peak concurrent executions observed — must stay 1 for a correct queue."""
        return self._max_observed_in_flight

    def pending(self) -> int:
        with self._lock:
            return max(self._submitted - self._completed - self._active, 0)

    def wait_until_idle(self, timeout_s: float | None = None) -> bool:
        import time

        deadline = None if timeout_s is None else time.monotonic() + timeout_s
        with self._lock:
            while self._active > 0 or (self._submitted - self._completed) > 0:
                if deadline is None:
                    self._lock.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._lock.wait(timeout=remaining)
        return True

    def shutdown(self, *, wait: bool = True) -> None:
        executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=wait, cancel_futures=not wait)
        with self._lock:
            self._submitted = self._completed = self._active = 0
            self._max_observed_in_flight = 0
            self._lock.notify_all()
