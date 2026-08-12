"""A minimal MCP backend over streamable HTTP, for tests that need one they can take away.

Serves exactly what the stdio bridge resolves against: `/api/stats` for the reachability probe, and a
streamable-HTTP MCP mount at `/mcp/read` carrying one tool. Deliberately not the product's backend —
the bridge forwards messages without reading them, so no repository content is involved, and this
starts in under a second where a real backend builds an index first.

Run as a script: `python tests/infrastructure/mcp/stub_mcp_backend.py <port>`.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

server = FastMCP("stub-read")


@server.tool()
def echo(text: str) -> str:
    """Return what it was given, so a call over the bridge has something to succeed at."""
    return text


# Builds the session manager the mount below serves; the product does the same before mounting.
server.streamable_http_app()


async def _stats(_request: Request) -> JSONResponse:
    return JSONResponse({"entities": 0})


@asynccontextmanager
async def _lifespan(_app: Starlette) -> AsyncIterator[None]:
    async with server.session_manager.run():
        yield


def build_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/api/stats", _stats),
            Route("/mcp/read", StreamableHTTPASGIApp(server.session_manager), methods=["GET", "POST", "DELETE"]),
        ],
        lifespan=_lifespan,
    )


if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
