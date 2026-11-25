"""Refuse a request addressed to a name this backend does not serve, before anything handles it.

The outermost layer of the application, so it covers the REST API, the event stream, the GUI's
files and the MCP mounts alike. What it allows is `src.config.allowed_hosts`, the list the MCP
transport settings are derived from too. The refusal is the bare answer a proxy or the MCP SDK
gives for the same case: a request that reaches it was not sent by this backend's own GUI, which is
always addressed by a name the backend serves, so there is no client to hand a typed envelope to.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.responses import PlainTextResponse

from src.config.allowed_hosts import ENV_ALLOWED_HOSTS, AllowedHosts, allowed_hosts

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

#: The status the MCP SDK answers the same refusal with, so every surface says one thing.
HOST_REFUSED_STATUS = 421


def _host_header(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"host":
            return str(value.decode("latin-1"))
    return None


class HostGuard:
    """ASGI middleware admitting only requests whose `Host` the configured list permits."""

    def __init__(self, app: ASGIApp, hosts: AllowedHosts | None = None) -> None:
        self.app = app
        self._hosts = hosts if hosts is not None else allowed_hosts()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or self._hosts.permits(_host_header(scope)):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        refusal = PlainTextResponse(
            f"Invalid Host header. This backend answers only to the names in {ENV_ALLOWED_HOSTS} "
            "and the loopback names.",
            status_code=HOST_REFUSED_STATUS,
        )
        await refusal(scope, receive, send)
