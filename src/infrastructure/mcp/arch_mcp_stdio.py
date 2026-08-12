"""STDIO bridge that connects an MCP client to the backend serving *this* workspace.

Which workspace that is has to be said, not inferred from a socket. The bridge asks for a backend
that serves the workspace it was pointed at (`--workspace`, `ARCH_MCP_WORKSPACE`, or the working
directory the client launched it in) and refuses rather than proxying into a stranger: an MCP client
shows a refusal, while a wrong-but-working connection looks exactly like a right one — a whole
session's reads and writes can land in a neighbouring checkout's model before anybody notices.

A bridge also has to say when it *stops* being able to proxy. Forwarding a request id is a promise to
deliver its answer, and a transport that has failed cannot keep that promise: the bridge answers the
ids itself and ends the process, so the client can relaunch it and re-run the checks above.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import NoReturn

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage

from src.infrastructure.backend.backend_launch import ensure_backend_running
from src.infrastructure.backend.backend_probe import backend_url, configured_backend_url
from src.infrastructure.mcp.bridge_replies import OutstandingReplies, failure_reason

logger = logging.getLogger(__name__)

#: Names the workspace this bridge serves, for clients that cannot set a working directory.
ENV_WORKSPACE = "ARCH_MCP_WORKSPACE"

#: Exit status for a connection that was established and then failed. Distinct from the refusal at
#: startup, so a client's log separates "never reached a backend" from "lost the one it had".
EXIT_CONNECTION_LOST = 3


def _project_directory() -> Path:
    return Path(__file__).resolve().parents[3]


def _workspace_directory(explicit: str | None) -> Path:
    """The workspace this bridge belongs to: the flag, the environment, then the working directory."""
    named = explicit or os.getenv(ENV_WORKSPACE, "").strip()
    return Path(named).expanduser().resolve() if named else Path.cwd()


async def _forward_client_requests(
    local_read: MemoryObjectReceiveStream[SessionMessage | Exception],
    remote_write: MemoryObjectSendStream[SessionMessage],
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
    remote_read: MemoryObjectReceiveStream[SessionMessage | Exception],
    local_write: MemoryObjectSendStream[SessionMessage],
    outstanding: OutstandingReplies,
) -> None:
    """Backend → client, ending the session when the transport hands over a failure instead of a reply.

    Reading on past one is what left a whole session hanging: the exception carries no id, so the
    request it belonged to can never be settled, and the client waits for a reply nothing will send.
    Raising it puts the reason in front of `_answer_and_stop`, which is where both are dealt with.
    """
    async with remote_read, local_write:
        async for message in remote_read:
            if isinstance(message, Exception):
                raise message
            outstanding.settle(message.message)
            await local_write.send(message)


def _answer_and_stop(outstanding: OutstandingReplies, failure: BaseException) -> NoReturn:
    """Answer what the backend no longer can, name the reason, and end the process.

    Ending it is what lets the client recover: a relaunched bridge re-runs the autostart with its
    health and workspace-identity checks, while this process holds a transport that will never carry
    another message.

    `os._exit`, deliberately. Returning cannot end the process here: `stdio_server` reads the client's
    stdin in an AnyIO worker thread, a thread blocked in `readline()` cannot be cancelled, and so the
    teardown around this handler waits for a line that a client waiting for a reply will never send —
    the observed failure was a bridge parked for five hours on one second of CPU. The replies are
    written and flushed before exiting, and the pumps are already torn down by the time this runs, so
    nothing else is queued to lose.
    """
    reason = failure_reason(failure)
    for message in outstanding.as_connection_closed(reason):
        sys.stdout.write(message.model_dump_json(by_alias=True, exclude_none=True) + "\n")
    sys.stdout.flush()
    print(f"arch-mcp-stdio: the backend connection failed ({reason}); exiting.", file=sys.stderr, flush=True)
    os._exit(EXIT_CONNECTION_LOST)


async def _run_bridge(url: str) -> None:
    outstanding = OutstandingReplies()
    async with stdio_server() as (local_read, local_write):
        try:
            async with streamablehttp_client(url) as (remote_read, remote_write, _get_session_id):
                async with anyio.create_task_group() as tg:
                    tg.start_soon(_forward_client_requests, local_read, remote_write, outstanding)
                    tg.start_soon(_forward_backend_replies, remote_read, local_write, outstanding)
        except* Exception as failure:
            _answer_and_stop(outstanding, failure)


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
