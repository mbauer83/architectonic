"""What this process owes on the way out, in the order it owes it.

Three modules, three jobs: ``shutdown`` holds the *policy* — the budgets, the signal, the step runner
— and names nothing this application contains; this module holds the *obligations*, which do; and
``arch_backend_app`` only wires them to a lifespan. Keeping the obligations here is what lets the
policy stay free of the assurance store, the write queue and git-sync, so every party can depend on
it and none has to depend on another.
"""

from __future__ import annotations

import logging

from src.infrastructure.artifact_index.coordination import get_write_queue_state_snapshot
from src.infrastructure.backend.shutdown import (
    WRITE_DRAIN_CEILING_SECONDS,
    WRITE_NO_PROGRESS_SECONDS,
    TeardownStep,
    shutdown_signal,
)

logger = logging.getLogger(__name__)


def teardown_steps(sync_mgr: object) -> list[TeardownStep]:
    """Everything this process owes on the way out, in the order it owes it.

    A named declaration rather than a literal inside the lifespan, because the order is the design
    and an order nothing can inspect is an order nothing can check. Read top to bottom:

    1. **Announce** — repeated here on purpose, and *not* what frees the connection drain: uvicorn
       waits for connections before running the teardown, so by now it is far too late.
       `_AnnouncingServer.handle_exit` announces in time. This covers shutdowns no signal starts —
       a `TestClient` lifespan, a programmatic stop — and is idempotent, so the two cannot conflict.
    2. **Drain writes** — before any store closes, because a write in flight is still using them.
    3. **Close the artifact index** — after the drain for that reason, and before the assurance store
       only because the two are independent and *some* order had to be written down.
    4. **Release the assurance store** — locks it, which checkpoints its write-ahead log.
    5. **Stop git-sync** — last: it is the only step whose work is external, and nothing above needs
       it to have stopped.

    `run_teardown` isolates each step, so a failure in one cannot skip the durability of another.
    """

    async def stop_git_sync() -> None:
        if sync_mgr is not None:
            await sync_mgr.stop()  # type: ignore[attr-defined]

    return [
        ("announce shutdown (already announced on a signal)", shutdown_signal.begin),
        ("drain in-flight writes", _drain_in_flight_writes),
        ("close the artifact index", _close_artifact_index),
        ("release the assurance store", _release_assurance_store),
        ("stop git-sync", stop_git_sync),
    ]


def _drain_in_flight_writes() -> None:
    """Let an artifact write that is already running finish before the process goes away.

    The last durability obligation the teardown did not name. By this point uvicorn has stopped
    accepting connections, so no *new* write can arrive — but one already in the serialized queue is
    mid-flight, and a multi-file change is published through a manifest precisely because a partially
    applied one leaves a repository that still parses and that no verifier reports. Waiting is what
    keeps that manifest from having to be the only defence.

    The wait is *adaptive*, not a flat timeout: it tolerates the queue being unchanged for
    `WRITE_NO_PROGRESS_SECONDS` under a hard ceiling, so a queue still completing jobs is waited on
    however long that takes while a stalled one still terminates. A fixed "wait N seconds for writes"
    would encode this machine's disk speed and this session's commit sizes, and would be wrong on a
    slower disk or a bulk write an order of magnitude larger.

    The wait itself belongs to `artifact_index.coordination`, which owns the queue's state; this only
    states the obligation and bounds it. Giving up is logged with what was still running, because
    "the write you issued may not have landed" is not something to leave silent — and it is degraded
    rather than unsafe, because a multi-file write is published through a manifest either way.
    """
    from src.infrastructure.artifact_index.coordination import (  # noqa: PLC0415
        wait_for_write_queue_drain,
    )

    drained = wait_for_write_queue_drain(
        timeout_s=WRITE_DRAIN_CEILING_SECONDS, no_progress_s=WRITE_NO_PROGRESS_SECONDS,
    )
    if not drained:
        logger.warning(
            "Shutdown: the write queue was still busy after %ss stalled (ceiling %ss); state=%s",
            WRITE_NO_PROGRESS_SECONDS, WRITE_DRAIN_CEILING_SECONDS,
            get_write_queue_state_snapshot(),
        )


def _close_artifact_index() -> None:
    """Release the index's database connections.

    A served process holds one shared-cache SQLite database per index, plus a pool of reader
    connections, for as long as it runs. Nothing closed them: `ArtifactIndex` had no `close`, so the
    only exit was the garbage collector, which is why 433 `ResourceWarning: unclosed database` appeared
    the moment warnings became errors. That is a leak the process could not help, not a test artefact.

    Through the repository facade rather than reaching for the index, because the facade is what the
    process holds. Skipped without complaint when no repository was ever installed — a backend that
    failed before `init_state` owes nothing here, and a teardown step that raised on that would mask
    whatever actually went wrong.
    """
    from src.infrastructure.rest.routers import state  # noqa: PLC0415

    repo = getattr(state, "_repo", None)
    if repo is not None:
        repo.close()


def _release_assurance_store() -> None:
    """Close the confidential store, which flushes its write-ahead log on the way out.

    ``lock()`` rather than a bare checkpoint, because both things this owes are the same call: the
    log is folded back into the file, and a process that is going away stops holding an authorised
    store open. It is the durability step — a process killed rather than asked leaves committed
    pages in ``store.db-wal`` that the next open may discard — and `run_teardown` isolates it so
    another step's failure cannot skip it.
    """
    from src.infrastructure.mcp.assurance_mcp.context import (  # noqa: PLC0415
        get_assurance_context,
    )

    store = getattr(get_assurance_context(), "store", None)
    if store is not None and getattr(store, "is_unlocked", lambda: False)():
        store.lock()
