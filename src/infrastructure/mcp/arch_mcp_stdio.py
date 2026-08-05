"""STDIO bridge that connects an MCP client to the backend serving *this* workspace.

Which workspace that is has to be said, not inferred from a socket. The bridge asks for a backend
that serves the workspace it was pointed at (`--workspace`, `ARCH_MCP_WORKSPACE`, or the working
directory the client launched it in) and refuses rather than proxying into a stranger: an MCP client
shows a refusal, while a wrong-but-working connection looks exactly like a right one — a whole
session's reads and writes can land in a neighbouring checkout's model before anybody notices.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage

from src.infrastructure.backend.backend_launch import ensure_backend_running
from src.infrastructure.backend.backend_probe import backend_url, configured_backend_url

logger = logging.getLogger(__name__)

#: Names the workspace this bridge serves, for clients that cannot set a working directory.
ENV_WORKSPACE = "ARCH_MCP_WORKSPACE"


def _project_directory() -> Path:
    return Path(__file__).resolve().parents[3]


def _workspace_directory(explicit: str | None) -> Path:
    """The workspace this bridge belongs to: the flag, the environment, then the working directory."""
    named = explicit or os.getenv(ENV_WORKSPACE, "").strip()
    return Path(named).expanduser().resolve() if named else Path.cwd()


async def _pump_reader_to_writer(
    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception],
    write_stream: MemoryObjectSendStream[SessionMessage],
) -> None:
    async with read_stream, write_stream:
        async for message in read_stream:
            if isinstance(message, Exception):
                logger.warning("MCP bridge: ignoring parse error from stream: %s", message)
                continue
            await write_stream.send(message)


async def _run_bridge(url: str) -> None:
    async with stdio_server() as (local_read, local_write):
        async with streamablehttp_client(url) as (remote_read, remote_write, _get_session_id):
            async with anyio.create_task_group() as tg:
                tg.start_soon(_pump_reader_to_writer, local_read, remote_write)
                tg.start_soon(_pump_reader_to_writer, remote_read, local_write)


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
