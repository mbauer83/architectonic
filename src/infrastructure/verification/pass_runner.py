"""Where a whole-repository verification pass runs, and what stops it.

FastMCP dispatches a synchronous tool directly on the event loop — `func_metadata` awaits an async
function and *calls* a sync one — so a pass that takes minutes takes the whole backend with it: no
identity check, no health probe, no event stream, until it returns. The pass therefore runs on a
worker of its own and the tool awaits it.

A worker **of its own**, not the default executor: `asyncio.to_thread` shares one pool with
git-status, group refreshes and every other offload in the process, and a pass sitting in it for
minutes starves them. Not a pool per call either, because verification already carries its own inner
`ThreadPoolExecutor` sized to the machine — that inner pool is the parallelism, and a per-call outer
pool would nest one inside the other.

Shutting down abandons rather than drains. A pass owes nothing durable: it reads, it reports, and a
half-finished one has written nothing to lose. Waiting for it would spend the stop budget on work
whose result nobody will receive.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import TypeVar

from src.application.verification.evaluation import PassCancellation
from src.infrastructure.concurrency.serial_execution_queue import SerialExecutionQueue

_T = TypeVar("_T")

verification_pass_queue = SerialExecutionQueue("verification-pass-queue")

_admission = threading.Lock()
_in_flight: dict[str, PassCancellation] = {}


class VerificationAlreadyRunning(Exception):
    """A pass over these roots is already in flight.

    Refused rather than queued, deliberately. Queuing a second pass over the same repository would
    make a caller wait minutes to be told what the first pass is about to say anyway, and a queue
    that accepts every duplicate is how a retrying client turns one slow answer into an hour of
    work. The refusal names the roots so the caller can wait for the answer it already asked for.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"a verification pass over {key} is already running")
        self.key = key


async def run_verification_pass(key: str, run: Callable[[PassCancellation], _T]) -> _T:
    """Run one pass over *key*'s roots on the verification worker, and await it.

    Raises :class:`VerificationAlreadyRunning` if one is already in flight over the same roots.
    Cancelling the awaiting task cancels the pass: the token *run* receives is set, the pass stops
    between files, and it saves nothing.
    """
    cancellation = PassCancellation()
    with _admission:
        if key in _in_flight:
            raise VerificationAlreadyRunning(key)
        _in_flight[key] = cancellation
    try:
        return await asyncio.wrap_future(verification_pass_queue.submit(run, cancellation))
    except asyncio.CancelledError:
        cancellation.cancel()
        raise
    finally:
        with _admission:
            _in_flight.pop(key, None)


def cancel_verification_passes() -> None:
    """Tell every pass in flight to stop between files."""
    with _admission:
        for cancellation in _in_flight.values():
            cancellation.cancel()


def abandon_verification_passes() -> None:
    """Stop verifying, without waiting for a pass in flight.

    Cancel first, then shut the worker down: cancelling asks the pass to stop at the next file and
    to write no state, and shutting down releases the thread. Doing only the second leaves the
    running pass to finish and save on the way out — which is the one thing a stopping process must
    not do, since the state it saves is a claim about files it may not have reached.
    """
    cancel_verification_passes()
    verification_pass_queue.shutdown(wait=False)
