"""Process-global single-writer queue for the confidential assurance store.

Every assurance mutation — from both the MCP write tools and the REST write
handlers — funnels through this one queue, so writes execute strictly one-at-a-time
(the audit-log ``seq`` allocation is a read-then-write race, and SQLite permits a
single writer). Reads do **not** go through the queue; they run concurrently over
the store's per-thread read connections.

This is a *separate* instance from the model write queue
(`mcp.artifact_mcp.write_queue`) so the two independent stores never falsely
serialise against each other (PLAN decision D3). Both share the same underlying
`SingleWriterQueue` mechanism.

Boundary helper: wrap the actual store/archive/connector write call in
``run_write(lambda: ...)`` inside each MCP tool / REST handler. Locked-state
checks and result translation stay on the calling thread; only the mutation runs
on the serialised worker.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from src.infrastructure.concurrency.single_writer_queue import SingleWriterQueue

_T = TypeVar("_T")

assurance_write_queue = SingleWriterQueue("assurance-write-queue")


def run_write(fn: Callable[..., _T], /, *args: Any, **kwargs: Any) -> _T:
    """Execute a single assurance write on the serialised single-writer worker."""
    return assurance_write_queue.run_sync(fn, *args, **kwargs)
