"""A bridge whose backend goes away answers the calls it accepted, and stops.

The failure this fixes was observed live: a bridge sat for five hours on one second of CPU while
nothing listened on its port, and the session that had opened it lost the whole toolset. Measured at
the wire level before the fix, a `tools/list` issued after the backend stopped got **no answer at all**
and the bridge stayed alive — no reply, no error, no EOF, so the client had nothing to react to.

Two levels here. The pumps are exercised over in-memory streams, because "which direction may read on
after an exception" is the decision the hang turned on. The last test drives the real bridge process
against a stub backend it then kills, because the previous version passed every in-process check the
suite had: the hang lived in what the *process* did after the transport failed.
"""

from __future__ import annotations

import json
import os
import selectors
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import anyio
import pytest
from mcp.shared.message import SessionMessage
from mcp.types import CONNECTION_CLOSED, JSONRPCMessage, JSONRPCRequest, JSONRPCResponse

from src.infrastructure.mcp.arch_mcp_stdio import (
    EXIT_CONNECTION_LOST,
    _forward_backend_replies,
    _forward_client_requests,
)
from src.infrastructure.mcp.bridge_replies import OutstandingReplies

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STUB_BACKEND = Path(__file__).resolve().parent / "stub_mcp_backend.py"
#: Generous against a loaded developer box; the measured answer takes milliseconds. Its only job is to
#: fail the test rather than hang the suite, which is the failure being guarded against.
_ANSWER_DEADLINE_SECONDS = 30.0
_STARTUP_DEADLINE_SECONDS = 60.0


def _request(request_id: int, method: str = "tools/list") -> SessionMessage:
    return SessionMessage(JSONRPCMessage(JSONRPCRequest(jsonrpc="2.0", id=request_id, method=method)))


def _response(request_id: int) -> SessionMessage:
    return SessionMessage(JSONRPCMessage(JSONRPCResponse(jsonrpc="2.0", id=request_id, result={})))


def _ids(messages: list[SessionMessage]) -> list[int | str]:
    """The request ids a pump passed on, so a test can name what crossed it."""
    addressed = []
    for message in messages:
        root = message.message.root
        assert isinstance(root, JSONRPCRequest | JSONRPCResponse), root
        addressed.append(root.id)
    return addressed


def test_a_client_line_that_is_not_json_rpc_is_reported_and_the_session_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The client is still there and its next line may be fine; only *this* line is unusable."""
    outstanding = OutstandingReplies()

    async def scenario() -> list[SessionMessage]:
        client_send, client_receive = anyio.create_memory_object_stream[SessionMessage | Exception](4)
        remote_send, remote_receive = anyio.create_memory_object_stream[SessionMessage](4)
        async with client_send:
            await client_send.send(ValueError("not json at all"))
            await client_send.send(_request(1, "artifact_verify"))
        await _forward_client_requests(client_receive, remote_send, outstanding)
        async with remote_receive:
            return [message async for message in remote_receive]

    forwarded = anyio.run(scenario)

    assert _ids(forwarded) == [1]
    assert "not json at all" in caplog.text
    # The request that *was* forwarded is owed an answer; the unusable line is owed nothing.
    assert len(outstanding.as_connection_closed("gone")) == 1


def test_a_failure_on_the_backend_stream_ends_the_session() -> None:
    """Reading on would leave the id it belonged to unanswered for ever: the exception carries none."""
    outstanding = OutstandingReplies()
    outstanding.accept(_request(1).message)

    async def scenario() -> None:
        remote_send, remote_receive = anyio.create_memory_object_stream[SessionMessage | Exception](4)
        client_send, client_receive = anyio.create_memory_object_stream[SessionMessage](4)
        # Closed before the pump runs, so a pump that read on instead of raising would *end*, and this
        # test would report that rather than waiting for a message nobody is going to send.
        async with remote_send:
            await remote_send.send(ConnectionError("stream broke"))
        async with client_receive:
            await _forward_backend_replies(remote_receive, client_send, outstanding)

    with pytest.raises(ConnectionError, match="stream broke"):
        anyio.run(scenario)


def test_a_delivered_reply_settles_its_request() -> None:
    outstanding = OutstandingReplies()
    outstanding.accept(_request(1).message)

    async def scenario() -> list[SessionMessage]:
        remote_send, remote_receive = anyio.create_memory_object_stream[SessionMessage | Exception](4)
        client_send, client_receive = anyio.create_memory_object_stream[SessionMessage](4)
        async with remote_send:
            await remote_send.send(_response(1))
        await _forward_backend_replies(remote_receive, client_send, outstanding)
        async with client_receive:
            return [message async for message in client_receive]

    delivered = anyio.run(scenario)

    assert _ids(delivered) == [1]
    assert outstanding.as_connection_closed("gone") == ()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def _stub_backend(log: Path) -> Iterator[tuple[subprocess.Popen[bytes], str]]:
    """A stub MCP backend on its own port, for as long as the test wants one."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    with log.open("wb") as sink:
        process = subprocess.Popen(
            [sys.executable, str(_STUB_BACKEND), str(port)],
            cwd=str(_REPO_ROOT),
            stdout=sink,
            stderr=subprocess.STDOUT,
        )
    with process:
        try:
            _await_stub(base_url, process, log)
            yield process, base_url
        finally:
            if process.poll() is None:
                process.kill()


def _await_stub(base_url: str, process: subprocess.Popen[bytes], log: Path) -> None:
    deadline = time.monotonic() + _STARTUP_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if (code := process.poll()) is not None:
            raise RuntimeError(f"stub backend exited with {code}:\n{log.read_text(errors='replace')}")
        try:
            with urllib.request.urlopen(f"{base_url}/api/stats", timeout=5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.25)
    raise RuntimeError(f"stub backend never served:\n{log.read_text(errors='replace')}")


def _send(bridge: subprocess.Popen[str], payload: dict[str, object]) -> None:
    assert bridge.stdin is not None
    bridge.stdin.write(json.dumps(payload) + "\n")
    bridge.stdin.flush()


def _read_reply(bridge: subprocess.Popen[str], deadline_s: float) -> dict[str, object] | None:
    """One JSON-RPC message from the bridge, or None if nothing arrives before the deadline."""
    assert bridge.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(bridge.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + deadline_s
    try:
        while time.monotonic() < deadline:
            if selector.select(timeout=0.25) and (line := bridge.stdout.readline()):
                parsed: dict[str, object] = json.loads(line)
                return parsed
        return None
    finally:
        selector.close()


@contextmanager
def _bridge_to(base_url: str, log: Path) -> Iterator[subprocess.Popen[str]]:
    """The real bridge process, connected to `base_url`, with JSON-RPC on its stdin and stdout."""
    with log.open("w") as sink:
        bridge = subprocess.Popen(
            [sys.executable, "-m", "src.infrastructure.mcp.arch_mcp_stdio", "--no-autostart"],
            cwd=str(_REPO_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sink,
            # The external URL is the one seam that reaches a backend without autostart, so the test
            # can never start — or adopt — the developer's own.
            env={**os.environ, "ARCH_MCP_BACKEND_URL": base_url},
            text=True,
            bufsize=1,
        )
    # `with` closes the pipes and reaps the process; killing first keeps its wait from being unbounded.
    with bridge:
        try:
            yield bridge
        finally:
            if bridge.poll() is None:
                bridge.kill()


def test_the_bridge_answers_a_call_its_backend_can_no_longer_serve(tmp_path: Path) -> None:
    with _stub_backend(tmp_path / "stub.log") as (backend, base_url):
        with _bridge_to(base_url, tmp_path / "bridge.log") as bridge:
            _send(bridge, {
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "bridge-regression", "version": "0"},
                },
            })
            assert _read_reply(bridge, _ANSWER_DEADLINE_SECONDS) is not None, "the bridge never connected"
            _send(bridge, {"jsonrpc": "2.0", "method": "notifications/initialized"})

            backend.terminate()
            backend.wait(timeout=30)

            _send(bridge, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            reply = _read_reply(bridge, _ANSWER_DEADLINE_SECONDS)

    # Before the fix this was None: no reply, and a process still running to wait in.
    assert reply is not None, "the bridge left the call unanswered"
    assert reply["id"] == 2
    error = reply["error"]
    assert isinstance(error, dict)
    assert error["code"] == CONNECTION_CLOSED
    # The reason is the point: "the backend went away" is actionable, "it failed" is not.
    assert "tools/list" in str(error["message"])
    assert bridge.wait(timeout=30) == EXIT_CONNECTION_LOST, "a bridge with a dead transport must stop"
