"""Write queue — serializes all model write operations through a single worker.

Concurrent write calls (artifact_create_entity, artifact_add_connection, etc.) race on
shared .md files and the SQLite index when issued in parallel. This module provides
a single-worker ThreadPoolExecutor that drains write operations serially: each call
is accepted immediately and returns its result as soon as it completes, but only one
write runs at a time.

Serialization is uniform across surfaces, but no caller reaches this module directly. MCP
mutation tools register through ``mutation_registration.register_mutation_tool``, whose
executor submits via ``submit_serialized`` and owns the workspace gate; REST handlers go
through ``routers.state.authorized_write``, which runs the same executor against the REST
mutation manifest. ``run_sync`` is the plain synchronous entry point for callers that
already hold the queue's context.

Serializing writes is not the same guarantee as landing one atomically. Durability is
classified separately, by blast radius: a single-file write is published by atomic
replacement, and a change spanning several files goes through an M4 manifest so it lands
whole. See ``write.artifact_write.file_transaction``.
"""

from __future__ import annotations

import asyncio
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from src.infrastructure.artifact_index.coordination import publish_write_queue_state
from src.infrastructure.write.operation_registry import operation_registry

_WRITE_EXECUTOR_WORKERS = 1

_executor: ThreadPoolExecutor | None = None
_state_cond = threading.Condition()
_submitted_jobs = 0
_completed_jobs = 0
_active_jobs = 0
_event_loop: asyncio.AbstractEventLoop | None = None
_active_tool_name: str | None = None
_active_operation_id: str | None = None
_active_phase: str | None = None


def attach_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store the running event loop so worker threads can schedule SSE notifications."""
    global _event_loop
    _event_loop = loop


def _notify_gui_dirty() -> None:
    """Emit sync_status_changed on the GUI event bus from a worker thread (best-effort)."""
    if _event_loop is None or not _event_loop.is_running():
        return
    try:
        from src.infrastructure.rest.routers.events import event_bus
        from src.infrastructure.rest.routers.sync.status_cache import invalidate_sync_status_cache

        invalidate_sync_status_cache()
        asyncio.run_coroutine_threadsafe(
            event_bus.publish({"type": "artifact_write_completed"}),
            _event_loop,
        )
    except Exception:
        pass


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _WRITE_EXECUTOR_WORKERS != 1:
        raise AssertionError("The architecture write executor must remain single-worker")
    if _executor is None or _executor._shutdown:
        _executor = ThreadPoolExecutor(
            max_workers=_WRITE_EXECUTOR_WORKERS,
            thread_name_prefix="model-write-queue",
        )
    return _executor


def _emit_queue_state() -> None:
    with _state_cond:
        publish_write_queue_state(
            active_jobs=_active_jobs,
            pending_jobs=max(_submitted_jobs - _completed_jobs - _active_jobs, 0),
            active_tool_name=_active_tool_name,
            active_operation_id=_active_operation_id,
            active_phase=_active_phase,
        )


def _run_job(tool_name: str, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    global _active_jobs, _completed_jobs
    global _active_tool_name, _active_operation_id, _active_phase
    with _state_cond:
        _active_jobs += 1
        _active_tool_name = tool_name
        _active_operation_id = None
        _active_phase = "running"
        publish_write_queue_state(
            active_jobs=_active_jobs,
            pending_jobs=max(_submitted_jobs - _completed_jobs - _active_jobs, 0),
            active_tool_name=_active_tool_name,
            active_operation_id=_active_operation_id,
            active_phase=_active_phase,
        )
    try:
        result = fn(*args, **kwargs)
        _notify_gui_dirty()
        return result
    finally:
        with _state_cond:
            _active_jobs -= 1
            _completed_jobs += 1
            if _active_jobs == 0:
                _active_tool_name = None
                _active_operation_id = None
                _active_phase = None
            publish_write_queue_state(
                active_jobs=_active_jobs,
                pending_jobs=max(_submitted_jobs - _completed_jobs - _active_jobs, 0),
                active_tool_name=_active_tool_name,
                active_operation_id=_active_operation_id,
                active_phase=_active_phase,
            )
            _state_cond.notify_all()


def _submit(tool_name: str, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
    global _submitted_jobs
    with _state_cond:
        _submitted_jobs += 1
        publish_write_queue_state(
            active_jobs=_active_jobs,
            pending_jobs=max(_submitted_jobs - _completed_jobs - _active_jobs, 0),
            active_tool_name=_active_tool_name,
            active_operation_id=_active_operation_id,
            active_phase=_active_phase,
        )
    return _get_executor().submit(_run_job, tool_name, fn, *args, **kwargs)


def submit_serialized(operation_name: str, fn: Callable[..., Any], /, *args: Any, **kwargs: Any):
    """Public submission port: schedule *fn* on the single write worker.

    Unlike ``queued``/``run_sync`` this takes NO gate — callers that need the
    workspace gate (the authorized mutation executor) acquire it inside the
    submitted job themselves, exactly once.
    """
    return _submit(operation_name, fn, *args, **kwargs)


def run_sync(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Execute a synchronous write through the shared single-worker queue.

    Acquires the workspace mutation gate inside the worker so the block check
    and execution are atomic.  Raises ``GateRejected`` if the gate is blocked;
    callers on the REST surface should convert this to HTTPException(423).
    """
    from src.infrastructure.workspace.mutation_gate import get_workspace_gate  # noqa: PLC0415

    gate = get_workspace_gate()
    fn_name = fn.__name__

    def _gated() -> Any:
        with gate.writing():
            return fn(*args, **kwargs)

    return _submit(fn_name, _gated).result()


def wait_until_idle(timeout_s: float | None = None) -> bool:
    import time

    deadline = None if timeout_s is None else time.monotonic() + timeout_s
    with _state_cond:
        while _active_jobs > 0 or (_submitted_jobs - _completed_jobs) > 0:
            if deadline is None:
                _state_cond.wait()
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _state_cond.wait(timeout=remaining)
    return True


def shutdown(wait: bool = True) -> None:
    """Shut down the write queue executor (for testing / clean teardown)."""
    global _executor, _submitted_jobs, _completed_jobs, _active_jobs
    global _active_tool_name, _active_operation_id, _active_phase
    if _executor is not None:
        _executor.shutdown(wait=wait, cancel_futures=True)
        _executor = None
    with _state_cond:
        _submitted_jobs = 0
        _completed_jobs = 0
        _active_jobs = 0
        _active_tool_name = None
        _active_operation_id = None
        _active_phase = None
        publish_write_queue_state(
            active_jobs=0,
            pending_jobs=0,
            active_tool_name=None,
            active_operation_id=None,
            active_phase=None,
        )
        _state_cond.notify_all()


def _handle_operation_registry_update(snapshot: dict[str, Any]) -> None:
    global _active_operation_id, _active_phase
    if not threading.current_thread().name.startswith("model-write-queue"):
        return
    with _state_cond:
        if _active_jobs <= 0:
            return
        _active_operation_id = snapshot.get("operation_id")
        phase = snapshot.get("phase")
        _active_phase = phase if isinstance(phase, str) else _active_phase
        publish_write_queue_state(
            active_jobs=_active_jobs,
            pending_jobs=max(_submitted_jobs - _completed_jobs - _active_jobs, 0),
            active_tool_name=_active_tool_name,
            active_operation_id=_active_operation_id,
            active_phase=_active_phase,
        )
        _state_cond.notify_all()


def _shutdown_atexit() -> None:
    """Best-effort executor teardown during interpreter shutdown.

    Avoid publishing queue-state events here; subscriber modules may already be
    partially torn down, and tests explicitly exercise the full shutdown path.
    """

    global _executor
    executor = _executor
    _executor = None
    if executor is not None:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


atexit.register(_shutdown_atexit)
operation_registry.subscribe(_handle_operation_registry_update)
