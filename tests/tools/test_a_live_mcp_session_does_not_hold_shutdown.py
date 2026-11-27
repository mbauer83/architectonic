"""A backend with an MCP session open still stops inside its budget.

The shutdown contract exists because one abandoned `/api/events` stream held the process open for
ever: uvicorn runs the lifespan teardown only after connections drain, and its default drain is
unbounded, so `--stop` escalated to SIGKILL every time — the one ending a WAL-mode encrypted store
must not get.

`/api/events` is not the only long-lived connection the backend serves. Four MCP mounts each hold a
streamable-HTTP session manager, entered in the lifespan and exited on the way out, and a client that
has initialised a session is holding one open. Draining an unrelated stream proves nothing about
those, so this opens a real session on a real backend and then stops it.

It earns its place from a migration rather than from an incident: `mcp` 2.x builds the session
manager lazily, inside `streamable_http_app()`, where 1.x had it from construction. That moved *when*
the four managers exist relative to the lifespan that runs them, and nothing else in the suite would
notice if a mount stopped being torn down — the process would simply take the long way to dying.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator

import pytest

from src.infrastructure.backend import backend_control
from src.infrastructure.backend.shutdown import STOP_DEADLINE_SECONDS
from tools.quality.fixture_backend import FixtureBackend, fixture_backend

#: Every mount, because the lifespan enters four session managers and a test on one proves one.
_MOUNTS = ("read", "write", "assurance-read", "assurance-write")


async def _open_a_session(url: str) -> str:
    """Initialise an MCP session and leave it open, answering which server it reached."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(url) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            await session.list_tools()
            return str(initialized.server_info.name)


class _Served:
    """One fixture backend for the module, started again only after a test has stopped it.

    Starting one builds a workspace and a store and waits for the process to answer, which is
    nearly all this module costs; the mounts only open sessions on it. The stop test *takes* the
    backend, so whatever runs after it is given a new one. One at a time: `fixture_backend` holds a
    cross-process lock for its whole life, so the previous one is let go before the next is started.
    """

    def __init__(self) -> None:
        self._stack = contextlib.ExitStack()
        self._backend: FixtureBackend | None = None

    def running(self) -> FixtureBackend:
        if self._backend is None:
            self.close()
            self._backend = self._stack.enter_context(fixture_backend())
        return self._backend

    def take(self) -> FixtureBackend:
        """The running backend, which the caller will stop: nobody else is handed it again."""
        backend = self.running()
        self._backend = None
        return backend

    def close(self) -> None:
        self._stack.close()
        self._stack = contextlib.ExitStack()


@pytest.fixture(scope="module")
def served() -> Iterator[_Served]:
    holder = _Served()
    try:
        yield holder
    finally:
        holder.close()


@pytest.mark.slow_walk
@pytest.mark.parametrize("mount", _MOUNTS)
def test_a_mount_answers_a_session_it_was_asked_for(mount: str, served: _Served) -> None:
    """The precondition: a session that never opened could not hold anything open either."""
    import anyio

    name = anyio.run(_open_a_session, f"{served.running().base_url}/mcp/{mount}")

    assert name, f"the {mount} mount answered no server name"


@pytest.mark.slow_walk
def test_the_process_stops_inside_its_budget_with_a_session_open(served: _Served) -> None:
    """The claim: an open MCP session does not push the stop past the contract's deadline.

    Measured against `STOP_DEADLINE_SECONDS` — the contract's own figure, derived from the drain and
    teardown budgets rather than restated here, so tightening one moves this with it.
    """
    import anyio

    backend = served.take()
    anyio.run(_open_a_session, f"{backend.base_url}/mcp/read")
    started = time.monotonic()
    # In the *fixture's* own name. Asked in the repository's name, the stop resolves to
    # whatever backend serves this workspace — the developer's, if one is running — and then
    # measures stopping a process this test never started.
    stopped = backend_control.stop_backend(
        cwd=backend.workspace.root, port=backend.port
    )
    took = time.monotonic() - started

    assert stopped, "the backend did not stop"
    assert took < STOP_DEADLINE_SECONDS, (
        f"stopping took {took:.1f}s against a {STOP_DEADLINE_SECONDS}s deadline with one MCP "
        "session open. A session manager that is not torn down holds the connection, and uvicorn "
        "waits for it before the lifespan teardown runs."
    )
