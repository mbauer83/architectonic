"""The shutdown contract: the budget, the signal, and the order of teardown.

Covers `backend.shutdown` and the three parties that consume it, because the defect these guard
against was never in any one of them — it was that the contract between them existed nowhere, so a
repair could land in whichever module the symptom appeared in and leave the mechanism unfixed.

The failure being prevented: uvicorn runs the lifespan teardown only after open connections drain,
`/api/events` streams until its client leaves, and uvicorn's default drain is unbounded. One
abandoned stream held the process open for ever — no "Shutting down", no teardown step, nothing in
the log between SIGTERM and death — and `backend_control` escalated to SIGKILL every time. SIGKILL is
the one ending a WAL-mode encrypted store must not get.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from contextlib import contextmanager

import pytest

from src.infrastructure.backend import backend_control
from src.infrastructure.backend.shutdown import (
    DRAIN_SECONDS,
    STOP_DEADLINE_SECONDS,
    TEARDOWN_SECONDS,
    ShutdownSignal,
    run_teardown,
    shutdown_signal,
)
from src.infrastructure.rest.routers.events import _HEARTBEAT_SECONDS, _event_stream, event_bus


@contextmanager
def _patched(target: str, replacement: object):
    """Swap a module attribute for the duration of a block, by dotted path."""
    module_path, _, attribute = target.rpartition(".")
    module = importlib.import_module(module_path)
    original = getattr(module, attribute)
    setattr(module, attribute, replacement)
    try:
        yield
    finally:
        setattr(module, attribute, original)


@pytest.fixture(autouse=True)
def _rearm_signal():
    """The signal is process-wide state; leaving it set would end every later test's streams."""
    shutdown_signal.reset()
    yield
    shutdown_signal.reset()


# ── The budget ────────────────────────────────────────────────────────────────


class TestTheBudgetIsOneDerivation:
    def test_the_stopper_waits_longer_than_the_process_is_allowed_to_take(self) -> None:
        """The ordering everything else rests on, in the direction that is easy to invert.

        An external stopper's wait must be the *longer* of the two. If the process may spend more
        than the stopper will wait, SIGKILL lands mid-teardown — and the teardown is what flushes the
        encrypted store. Two hand-tuned numbers drift into exactly that, so one is derived.
        """
        assert STOP_DEADLINE_SECONDS == DRAIN_SECONDS + TEARDOWN_SECONDS
        assert STOP_DEADLINE_SECONDS > DRAIN_SECONDS
        assert TEARDOWN_SECONDS > 0, "the teardown needs time of its own, or both deadlines coincide"

    def test_the_stop_path_takes_its_deadline_from_the_contract(self) -> None:
        """Not its own constant. `backend_control` holding a private timeout is how the two came
        apart in the first place."""
        for function in (backend_control.stop_backend, backend_control._stop_pid):
            default = inspect.signature(function).parameters["timeout_s"].default
            assert default == STOP_DEADLINE_SECONDS, f"{function.__name__} has its own deadline"

    def test_the_server_is_launched_with_a_bounded_drain(self) -> None:
        """uvicorn's default is to wait for open connections for ever, and that default is what let
        one abandoned event stream make SIGTERM a no-op. Asserted on the Config the launch builds,
        so it exercises the real path rather than restating the source."""
        import uvicorn

        from src.infrastructure.backend import arch_backend

        launched: list[uvicorn.Server] = []
        original = uvicorn.Server.run
        uvicorn.Server.run = lambda self, sockets=None: launched.append(self)  # type: ignore[assignment,misc]
        try:
            arch_backend._serve(lambda *_a: None, host="127.0.0.1", port=8123)
        finally:
            uvicorn.Server.run = original  # type: ignore[assignment,misc]

        assert len(launched) == 1
        server = launched[0]
        assert isinstance(server, arch_backend._AnnouncingServer), (
            "a plain uvicorn.Server never announces the stop, so the streams would only be severed"
        )
        assert server.config.timeout_graceful_shutdown == DRAIN_SECONDS
        assert server.config.port == 8123

    def test_the_signal_is_announced_before_uvicorn_starts_draining(self) -> None:
        """The clause the whole mechanism rests on, and the one that was silently wrong.

        uvicorn waits for open connections *before* running the lifespan teardown, so announcing
        from the teardown reaches the event streams only after the drain has given up on them. The
        real log said it: ``Cancel 3 running task(s), timeout graceful shutdown exceeded``, and the
        announcement after. The streams were being severed, not ending themselves, and every unit
        test still passed because they call ``begin()`` directly.

        So the announcement is asserted at uvicorn's own signal seam. If it moves back into the
        teardown, this fails — which is what the earlier version had no way to say.
        """
        import signal as signal_module

        import uvicorn

        from src.infrastructure.backend.arch_backend import _AnnouncingServer

        server = _AnnouncingServer(uvicorn.Config(app=lambda *a: None))
        assert not shutdown_signal.is_set()

        server.handle_exit(signal_module.SIGTERM, None)

        assert shutdown_signal.is_set(), "the streams were not told before the drain began"
        # And uvicorn's own handling still ran: announcing must not replace it.
        assert server.should_exit is True

    def test_a_heartbeat_cannot_fit_inside_the_drain_budget(self) -> None:
        """Why the stream races the signal against its queue instead of polling on the heartbeat."""
        assert _HEARTBEAT_SECONDS > DRAIN_SECONDS


# ── The signal ────────────────────────────────────────────────────────────────


class TestTheSignalIsObservableFromAnyLoop:
    def test_a_waiter_created_after_the_announcement_is_already_set(self) -> None:
        """A connection accepted during shutdown must not wait for a second announcement."""

        async def _run() -> None:
            signal = ShutdownSignal()
            signal.begin()
            assert signal.waiter().is_set()

        asyncio.run(_run())

    def test_the_same_signal_serves_a_second_event_loop(self) -> None:
        """The regression behind the design. A module-level `asyncio.Event` binds to the first loop
        that waits on it; a second loop in the same process then raises "bound to a different event
        loop" and the waiter never learns it should stop. Each waiter is created in its own loop.
        """
        signal = ShutdownSignal()

        async def _observe() -> bool:
            waiter = signal.waiter()
            signal.begin()
            await asyncio.wait_for(waiter.wait(), timeout=1.0)
            signal.reset()
            return True

        assert asyncio.run(_observe())
        assert asyncio.run(_observe()), "a second loop must work as well as the first"

    def test_waiters_do_not_accumulate_per_connection(self) -> None:
        """One entry per connection served, never released, is a leak in a long-lived process."""

        async def _run() -> None:
            signal = ShutdownSignal()
            waiter = signal.waiter()
            signal.release(waiter)
            signal.begin()
            assert not waiter.is_set(), "a released waiter is no longer the signal's concern"

        asyncio.run(_run())


# ── The streams that decide when teardown may begin ───────────────────────────


class TestOpenStreamsEndOnTheSignal:
    def test_an_open_stream_ends_when_the_process_starts_stopping(self) -> None:
        """The property SIGTERM depends on. Without it the generator never returns, the connection
        never closes, and the teardown that flushes the assurance store never runs."""

        async def _run() -> None:
            queue = await event_bus.subscribe()
            stream = _event_stream(queue)

            await event_bus.publish({"type": "artifact_write_completed", "repo": "engagement"})
            first = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert first.startswith("event: artifact_write_completed")

            shutdown_signal.begin()
            final = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            assert final == "event: shutdown\ndata: {}\n\n"
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(stream.__anext__(), timeout=2.0)

        asyncio.run(_run())

    def test_a_stream_idle_on_its_queue_ends_well_inside_the_drain_budget(self) -> None:
        """A stream parked in `queue.get()` — an idle browser tab — used to be unreachable until its
        next heartbeat, which is longer than the whole drain budget."""

        async def _run() -> None:
            queue = await event_bus.subscribe()
            stream = _event_stream(queue)
            started = asyncio.get_running_loop().time()

            async def stop_shortly() -> None:
                await asyncio.sleep(0.05)
                shutdown_signal.begin()

            task = asyncio.ensure_future(stop_shortly())
            final = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
            await task

            assert final == "event: shutdown\ndata: {}\n\n"
            elapsed = asyncio.get_running_loop().time() - started
            assert elapsed < DRAIN_SECONDS, f"took {elapsed:.2f}s of a {DRAIN_SECONDS}s budget"

        asyncio.run(_run())

    def test_a_finished_stream_unsubscribes_itself(self) -> None:
        """A subscriber left on the bus is a queue publishes fill and then start dropping from."""

        async def _run() -> None:
            queue = await event_bus.subscribe()
            stream = _event_stream(queue)
            shutdown_signal.begin()
            async for _frame in stream:
                pass
            # Reaching into the bus deliberately: the leak is invisible from the frames, and only
            # shows up later as events silently dropped for every other subscriber.
            assert queue not in event_bus._subscribers

        asyncio.run(_run())


# ── The teardown ──────────────────────────────────────────────────────────────


class TestTeardownRunsEveryStepInOrder:
    def test_steps_run_in_the_declared_order(self) -> None:
        """Order is load-bearing: the signal has to be announced before anything waits on the
        connections it releases. That is why this is a sequence and not a gather."""
        ran: list[str] = []
        asyncio.run(run_teardown([
            ("first", lambda: ran.append("first")),
            ("second", lambda: ran.append("second")),
        ]))
        assert ran == ["first", "second"]

    def test_a_failing_step_does_not_strand_the_steps_after_it(self) -> None:
        """The regression. One of these steps is durability; before isolation, a git-sync stop that
        threw took the assurance store's flush with it and neither appeared in the log."""
        ran: list[str] = []

        def explode() -> None:
            raise RuntimeError("teardown step failed")

        asyncio.run(run_teardown([
            ("boom", explode),
            ("durability", lambda: ran.append("durability")),
        ]))
        assert ran == ["durability"]

    def test_the_declared_order_drains_writes_before_any_store_closes(self) -> None:
        """The order is the design, so it is asserted rather than left to reading.

        A write in flight is still using the stores, so it has to finish before they close; the
        announcement has to come first for the shutdowns no signal starts; git-sync goes last because
        nothing above it needs it stopped.
        """
        from src.infrastructure.backend._teardown import teardown_steps

        labels = [label for label, _step in teardown_steps(sync_mgr=None)]
        assert labels[0].startswith("announce")
        assert labels.index("drain in-flight writes") < labels.index("release the assurance store")
        assert labels[-1] == "stop git-sync"

    def test_a_write_that_does_not_drain_in_time_is_reported(self, caplog) -> None:
        """"The write you issued may not have landed" is not something to leave silent. The wait is
        bounded because the stopper's deadline is; what it must not be is quiet."""
        import logging

        from src.infrastructure.backend import _teardown

        with caplog.at_level(logging.WARNING):
            with _patched(
                "src.infrastructure.artifact_index.coordination.wait_for_write_queue_drain",
                lambda timeout_s=None, no_progress_s=None: False,
            ):
                _teardown._drain_in_flight_writes()
        assert any("still busy" in record.getMessage() for record in caplog.records)

    def test_the_write_drain_budget_leaves_room_for_the_steps_after_it(self) -> None:
        """The drain is the only teardown step that can take real time. If it could consume the whole
        teardown budget, the durability steps behind it would run past the stopper's deadline — which
        is the SIGKILL this whole contract exists to avoid."""
        from src.infrastructure.backend.shutdown import (
            WRITE_DRAIN_CEILING_SECONDS,
            WRITE_NO_PROGRESS_SECONDS,
        )

        assert 0 < WRITE_DRAIN_CEILING_SECONDS < TEARDOWN_SECONDS
        assert DRAIN_SECONDS + WRITE_DRAIN_CEILING_SECONDS < STOP_DEADLINE_SECONDS
        # The stall patience has to fit inside the ceiling, or it can never be what ends the wait and
        # the drain is absolute again in everything but name.
        assert 0 < WRITE_NO_PROGRESS_SECONDS < WRITE_DRAIN_CEILING_SECONDS

    def test_an_async_step_is_awaited(self) -> None:
        """`sync_mgr.stop()` is a coroutine; a step runner that only called it would leave the
        manager running and report the step complete."""
        ran: list[str] = []

        async def stop() -> None:
            await asyncio.sleep(0)
            ran.append("stopped")

        asyncio.run(run_teardown([("async step", stop)]))
        assert ran == ["stopped"]
