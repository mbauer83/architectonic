"""How this process stops: the budget, the signal, and the order of teardown.

Stopping the backend is a contract between four parties, and it used to be written down nowhere:

* ``arch_backend`` starts uvicorn, which owns the signal handlers;
* ``arch_backend_app``'s lifespan releases the resources;
* ``routers.events`` serves connections that decide when the release may begin;
* ``backend_control`` sends the signal from *outside* the process and escalates.

Each held one clause, none held the whole, and so each repair landed in whichever module the symptom
appeared in. This module is the contract. Nothing here knows about routers, apps or processes — it is
policy, a signal, and a step runner — so every party can depend on it and none has to depend on
another.

**What went wrong, once, so it is not re-diagnosed.** uvicorn runs the lifespan teardown only after
open connections drain, and ``/api/events`` is a server-sent-event stream that loops until its client
leaves. One abandoned stream — a closed laptop, a leaked browser page — held the drain open for ever.
The process logged *nothing* between SIGTERM and its death: not uvicorn's "Shutting down", not a
single teardown step. ``backend_control`` waited, gave up, and sent SIGKILL. Adding that escalation
made ``--stop`` *return*; it never made the process *stop*, and SIGKILL is the one ending a WAL-mode
encrypted store must not get, because unflushed pages in the write-ahead log are committed writes the
next open may discard.

So the three clauses below are one design, not three fixes:

1. :data:`DRAIN_SECONDS` bounds what uvicorn may spend waiting for connections. Its default is
   "for ever", which is what made a single stream fatal.
2. :class:`ShutdownSignal` lets in-process components end themselves the moment the signal arrives,
   so the drain finishes because the connections *closed*, not because a deadline expired.
3. :func:`run_teardown` releases resources in a declared order, isolating each step, so a failure in
   one cannot skip the ones after it — the durability step included.

And :data:`STOP_DEADLINE_SECONDS` is *derived* from the first two rather than tuned beside them: an
external stopper has to wait longer than the process is permitted to take, or its escalation lands
mid-teardown and undoes the point of having one.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)

#: How long uvicorn may spend waiting for open connections after a signal, before closing them
#: itself. A bound, not a target: the streams end themselves, and this only covers what does not.
DRAIN_SECONDS = 5

#: How long the resource teardown is expected to need once the connections are gone — stopping
#: git-sync, closing the MCP session managers, flushing the assurance store.
TEARDOWN_SECONDS = 5

#: How long an external stopper waits after SIGTERM before escalating to SIGKILL.
#:
#: Derived, deliberately. It must exceed everything the process is allowed to spend, or the
#: escalation arrives while the teardown is still running — and two independently-chosen numbers
#: drift into exactly that, which is how a SIGKILL became the normal way this backend ended.
STOP_DEADLINE_SECONDS = DRAIN_SECONDS + TEARDOWN_SECONDS


class ShutdownSignal:
    """"The process is stopping" — observable from any number of coroutines, in any loop.

    A single module-level :class:`asyncio.Event` is the obvious implementation and it is wrong: an
    Event binds to the first loop that waits on it, so a second loop in the same process — a test's,
    or a reload — raises ``RuntimeError: bound to a different event loop`` and the waiter never
    learns it should stop. The flag is therefore plain state, and each waiter gets an Event created
    in its own loop.
    """

    def __init__(self) -> None:
        self._stopping = False
        self._waiters: set[asyncio.Event] = set()

    def is_set(self) -> bool:
        return self._stopping

    def begin(self) -> None:
        """Announce the stop and wake everything waiting on it. Idempotent."""
        self._stopping = True
        for waiter in list(self._waiters):
            waiter.set()

    def reset(self) -> None:
        """Re-arm. For tests, and for a lifespan that runs again in the same process."""
        self._stopping = False
        self._waiters.clear()

    def waiter(self) -> asyncio.Event:
        """An Event for the calling loop, already set if the stop has been announced.

        Register with :meth:`release` when done, or the set grows one entry per connection served.
        """
        waiter = asyncio.Event()
        if self._stopping:
            waiter.set()
        self._waiters.add(waiter)
        return waiter

    def release(self, waiter: asyncio.Event) -> None:
        self._waiters.discard(waiter)


#: The process's signal. One per process because there is one process-wide stop.
shutdown_signal = ShutdownSignal()

#: One named teardown step: a label for the log, and the work.
TeardownStep = tuple[str, Callable[[], object]]


async def run_teardown(steps: Sequence[TeardownStep]) -> None:
    """Run every step in order, isolating failures, logging each.

    Isolated because the steps are independent obligations and one of them is durability. Before
    this, a raising step skipped every step after it: a git-sync stop that threw would take the
    assurance store's flush with it, and the log would show neither. Ordering still matters — the
    signal has to be announced before anything waits on connections — so this is a sequence, not a
    gather.

    Steps may be sync or async; a coroutine result is awaited.
    """
    for label, step in steps:
        try:
            result = step()
            if asyncio.iscoroutine(result):
                await result
        except Exception:  # noqa: BLE001 - one step's failure must not strand the others
            logger.warning("Shutdown step %r failed; continuing", label, exc_info=True)
        else:
            logger.info("Shutdown step %r complete", label)
