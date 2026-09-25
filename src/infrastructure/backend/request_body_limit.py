"""Refuse a request body larger than the operation it addresses reads, before reading it (D7).

The limit is the route-policy row's `max_body_bytes`, or the default for a row that names none: a
body no operation could want is never read into memory. A body that declares its length is refused
on the declaration; one sent in chunks is counted as it arrives and refused once it passes the limit,
so leaving the length out is no way round it. Either way the answer is the shared error envelope,
`request_too_large`, carrying the limit so a caller knows how much less to send.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from src.infrastructure.rest.contracts.error_responses import REQUEST_ID_HEADER, api_error_response
from src.infrastructure.rest.contracts.errors import ApiError, RequestTooLargeDetails
from src.infrastructure.rest.route_policy import body_limit_for

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_METHODS_WITH_BODIES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class _TooLarge(Exception):
    pass


class RequestBodyLimit:
    """ASGI middleware applying each operation's body limit."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _METHODS_WITH_BODIES:
            await self.app(scope, receive, send)
            return
        limit = body_limit_for(scope["method"], scope["path"])
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _refuse(scope, send, limit)
            return
        received = 0

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge
            return message

        try:
            await self.app(scope, counted, send)
        except _TooLarge:
            # Every operation reads its body before it answers, so nothing has been sent yet.
            await _refuse(scope, send, limit)


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _request_id(scope: Scope) -> str:
    wanted = REQUEST_ID_HEADER.lower().encode("latin-1")
    for name, value in scope.get("headers", []):
        if name == wanted and value:
            return str(value.decode("latin-1"))
    return uuid.uuid4().hex


async def _refuse(scope: Scope, send: Send, limit: int) -> None:
    refusal = ApiError(
        413, "request_too_large",
        f"The request body is larger than this operation accepts ({limit} bytes)",
        RequestTooLargeDetails(max_body_bytes=limit),
    )
    response = api_error_response(refusal, request_id=_request_id(scope))

    async def nothing_more() -> Message:
        return {"type": "http.disconnect"}

    await response(scope, nothing_more, send)
