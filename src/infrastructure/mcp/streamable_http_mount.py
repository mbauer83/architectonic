"""How an MCP server is reached over streamable HTTP — one owner for all four mounts.

In `mcp` 1.x the transport belonged to the server: `host`, `port`, `streamable_http_path`,
`json_response`, `stateless_http` and `transport_security` were constructor arguments, so each server
module carried its own copy of the same environment reads. 2.x moved them to
``MCPServer.streamable_http_app()``, where they belong — a server is what answers, and the transport
is how it is reached — and that made the duplication removable rather than merely visible.

So the four mounts are configured here, once. The path stays with the mount rather than the server,
because it is an address in this application's URL space and nothing about the server depends on it.

**Why the ASGI handler and not the Starlette app.** ``streamable_http_app()`` returns a Starlette
application routing its own ``streamable_http_path``, and Starlette mounts match ``/mcp/read/…`` but
not the bare ``/mcp/read``. The backend serves both spellings so an IDE client can POST to either, so
it routes the handler itself. Calling ``streamable_http_app()`` is still what creates the session
manager — it is built lazily, and asking for it first raises.
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp

from src.infrastructure.mcp.transport_security import build_transport_security

#: Values a boolean environment variable may take. One spelling, so two servers cannot disagree.
_TRUE = {"1", "true", "TRUE", "yes", "YES"}


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default) in _TRUE


def host() -> str:
    """The host the transport answers on. Seeds the SDK's DNS-rebinding defaults."""
    return os.getenv("ARCH_MCP_HOST", "127.0.0.1")


def log_level() -> str:
    """The one server-construction setting that is not about the transport."""
    return os.getenv("ARCH_MCP_LOG_LEVEL", "INFO")


def mounted(server: MCPServer, path: str) -> StreamableHTTPASGIApp:
    """Configure the server's streamable-HTTP transport, and hand back the handler to route to."""
    server.streamable_http_app(
        streamable_http_path=path,
        json_response=_flag("ARCH_MCP_JSON_RESPONSE", "0"),
        stateless_http=_flag("ARCH_MCP_STATELESS_HTTP", "1"),
        transport_security=build_transport_security(),
        host=host(),
    )
    return StreamableHTTPASGIApp(server.session_manager)
