"""STDIO bridge that connects an MCP client to the backend serving *this* workspace.

Which workspace that is has to be said, not inferred from a socket. The bridge asks for a backend
that serves the workspace it was pointed at (`--workspace`, `ARCH_MCP_WORKSPACE`, or the working
directory the client launched it in) and refuses rather than proxying into a stranger: an MCP client
shows a refusal, while a wrong-but-working connection looks exactly like a right one — a whole
session's reads and writes can land in a neighbouring checkout's model before anybody notices.

A bridge also has to say when it *stops* being able to proxy. Forwarding a request id is a promise to
deliver its answer, and a transport that has failed cannot keep that promise: the bridge answers the
ids itself and ends the process, so the client can relaunch it and re-run the checks above.

A backend that restarts is the same loss by another route. The transport still connects, but the
new process does not know the session the bridge holds and answers every request for it with 404.
The bridge treats that answer as the end of its connection, because no later request can succeed on
that session and the client has to reconnect to read the restarted backend's tools.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import NoReturn

import anyio
import httpx2
from mcp.client.streamable_http import MCP_SESSION_ID, create_mcp_http_client, streamable_http_client
from mcp.server.stdio import stdio_server
from mcp.shared._stream_protocols import ReadStream, WriteStream
from mcp.shared.message import SessionMessage

from src.infrastructure.backend.backend_launch import ensure_backend_running
from src.infrastructure.backend.backend_probe import backend_url, configured_backend_url
from src.infrastructure.mcp.bridge_replies import OutstandingReplies, failure_reason

# `ReadStream` / `WriteStream` are the SDK's own stream protocols. Both ends of this bridge are typed
# by them in `mcp` 2.x — `stdio_server` and `streamable_http_client` hand over context-carrying
# streams rather than the anyio memory pair they used to be — and the public re-exports cover only
# the reading half, so the definitions are taken from where the SDK states them.

logger = logging.getLogger(__name__)

#: Names the workspace this bridge serves, for clients that cannot set a working directory.
ENV_WORKSPACE = "ARCH_MCP_WORKSPACE"

#: Exit status for a connection that was established and then failed. Distinct from the refusal at
#: startup, so a client's log separates "never reached a backend" from "lost the one it had".
EXIT_CONNECTION_LOST = 3


class BackendSessionEnded(Exception):
    """The backend no longer knows the session this bridge holds: it was restarted under it."""

    def __init__(self) -> None:
        super().__init__("the backend was restarted; restart or reconnect this MCP client to pick up its tools")


class BackendSession:
    """Whether the backend still recognises the session this bridge opened.

    Read from the HTTP status rather than from the JSON-RPC error the SDK hands over for it. The MCP
    specification states the fact at this level: a server answers 404 to a request that names a
    session it does not hold. The SDK turns that 404 into an error reply whose wording depends on
    whether the server sent a body, so the wording is not something to match on. Observed as a
    response hook, which runs before the SDK reads the response, so the flag is set before the error
    reply reaches `_forward_backend_replies`.
    """

    def __init__(self) -> None:
        self._ended = False

    @property
    def ended(self) -> bool:
        return self._ended

    async def observe(self, response: httpx2.Response) -> None:
        """Note a 404 to a request that named a session. A 404 before any session has no such meaning."""
        if response.status_code == 404 and MCP_SESSION_ID in response.request.headers:
            self._ended = True


def _project_directory() -> Path:
    return Path(__file__).resolve().parents[3]


def _workspace_directory(explicit: str | None) -> Path:
    """The workspace this bridge belongs to: the flag, the environment, then the working directory."""
    named = explicit or os.getenv(ENV_WORKSPACE, "").strip()
    return Path(named).expanduser().resolve() if named else Path.cwd()


async def _forward_client_requests(
    local_read: ReadStream[SessionMessage | Exception],
    remote_write: WriteStream[SessionMessage],
    outstanding: OutstandingReplies,
) -> None:
    """Client → backend, recording each request id so the bridge can answer it if the backend cannot.

    An exception here is a line from the client that is not a JSON-RPC message. It carries no id, so
    there is nothing to answer and nothing is wrong with the connection: name it and read on.
    """
    async with local_read, remote_write:
        async for message in local_read:
            if isinstance(message, Exception):
                logger.warning("MCP bridge: the client sent a line that is not JSON-RPC: %s", message)
                continue
            outstanding.accept(message.message)
            await remote_write.send(message)


async def _forward_backend_replies(
    remote_read: ReadStream[SessionMessage | Exception],
    local_write: WriteStream[SessionMessage],
    outstanding: OutstandingReplies,
    session: BackendSession,
) -> None:
    """Backend → client, ending the session when the transport hands over a failure instead of a reply.

    Reading on past one is what left a whole session hanging: the exception carries no id, so the
    request it belonged to can never be settled, and the client waits for a reply nothing will send.
    Raising it puts the reason in front of `_answer_and_stop`, which is where both are dealt with.

    A session the backend no longer holds is a failure of the same kind. The reply that reports it is
    not forwarded: its request stays outstanding, so `_answer_and_stop` answers it with the reason.
    """
    async with remote_read, local_write:
        async for message in remote_read:
            if isinstance(message, Exception):
                raise message
            if session.ended:
                raise BackendSessionEnded()
            outstanding.settle(message.message)
            await local_write.send(message)


def _answer_and_stop(outstanding: OutstandingReplies, failure: BaseException, *, channel: int) -> NoReturn:
    """Answer what the backend no longer can, name the reason, and end the process.

    Ending it is what lets the client recover: a relaunched bridge re-runs the autostart with its
    health and workspace-identity checks, while this process holds a transport that will never carry
    another message.

    `channel` is a duplicate of the process's real stdout, taken before `stdio_server()` started.
    While it serves, `stdio_server` points file descriptor 1 at stderr so that stray output from a
    handler or a child cannot corrupt the protocol stream. These replies are not stray output — they
    are the answers this bridge owes — so writing them through `sys.stdout` would send the client's
    last word to a log instead of to the client, which is the whole failure this function exists to
    prevent. Written with `os.write` for the same reason: the descriptor is the channel.

    `os._exit`, deliberately. Returning cannot end the process here: `stdio_server` reads the client's
    stdin in an AnyIO worker thread, a thread blocked in `readline()` cannot be cancelled, and so the
    teardown around this handler waits for a line that a client waiting for a reply will never send —
    the observed failure was a bridge parked for five hours on one second of CPU. The replies are
    written before exiting, and the pumps are already torn down by the time this runs, so nothing
    else is queued to lose.
    """
    reason = failure_reason(failure)
    payload = "".join(
        message.model_dump_json(by_alias=True, exclude_none=True) + "\n"
        for message in outstanding.as_connection_closed(reason)
    ).encode("utf-8")
    while payload:
        payload = payload[os.write(channel, payload):]
    print(f"arch-mcp-stdio: the backend connection failed ({reason}); exiting.", file=sys.stderr, flush=True)
    os._exit(EXIT_CONNECTION_LOST)


#: How long the bridge will spend trying to *reach* a backend before it answers what it owes.
#: The SDK's default is 30 seconds, which is a reasonable budget for a remote server and a poor one
#: for a process on this machine: a client asking a bridge whose backend has gone waits out the whole
#: budget for a reply that was never coming. Reading is left long, because a tool call legitimately
#: takes a while and cutting one short would be a worse answer than a slow one.
CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 300.0


async def _run_bridge(url: str) -> None:
    outstanding = OutstandingReplies()
    session = BackendSession()
    # Taken before `stdio_server()` claims file descriptor 1 — see `_answer_and_stop`.
    channel = os.dup(1)
    async with stdio_server() as (local_read, local_write):
        try:
            timeout = httpx2.Timeout(
                CONNECT_TIMEOUT_SECONDS, read=READ_TIMEOUT_SECONDS, write=CONNECT_TIMEOUT_SECONDS,
                pool=CONNECT_TIMEOUT_SECONDS,
            )
            # Two streams, not three: `mcp` 2.x dropped the session-id accessor, which this
            # bridge never used — it forwards messages without reading their session. Whether the
            # backend still holds that session is read from the HTTP status, by `BackendSession`.
            async with create_mcp_http_client(timeout=timeout) as http_client:
                hooks = http_client.event_hooks
                http_client.event_hooks = {**hooks, "response": [*hooks["response"], session.observe]}
                async with streamable_http_client(url, http_client=http_client) as (remote_read, remote_write):
                    async with anyio.create_task_group() as tg:
                        tg.start_soon(_forward_client_requests, local_read, remote_write, outstanding)
                        tg.start_soon(_forward_backend_replies, remote_read, local_write, outstanding, session)
        except* Exception as failure:
            _answer_and_stop(outstanding, failure, channel=channel)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="arch-mcp-stdio")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-autostart", action="store_true", default=False)
    parser.add_argument(
        "--server",
        choices=("read", "write", "assurance-read", "assurance-write"),
        default="read",
        help="Which MCP server to connect to",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        metavar="DIR",
        help=f"Workspace directory this bridge serves (default: ${ENV_WORKSPACE} or the working directory)",
    )
    args = parser.parse_args(argv)

    project_dir = _project_directory()
    workspace_dir = _workspace_directory(args.workspace)
    try:
        port = ensure_backend_running(
            port=args.port,
            start_if_missing=not args.no_autostart,
            cwd=workspace_dir,
            project_dir=project_dir,
        )
    except RuntimeError as exc:
        raise SystemExit(
            f"arch-mcp-stdio: no backend available for the workspace at {workspace_dir}.\n{exc}\n"
            f"If this bridge should serve a different workspace, pass --workspace or set {ENV_WORKSPACE}."
        ) from exc
    target_base = configured_backend_url() or backend_url(port)
    print(f"arch-mcp-stdio: workspace {workspace_dir} → {target_base}/mcp/{args.server}", file=sys.stderr)
    anyio.run(_run_bridge, f"{target_base}/mcp/{args.server}")


if __name__ == "__main__":
    main()
