"""Apply each operation's declared ``Cache-Control`` directive, from the route-policy manifest.

Caching is two independent decisions, and this module carries the first one. Whether a response may
be *stored* is `cache_directive`; whether it may be *revalidated* is `conditional_read`, which
``read_model_caching`` implements. Setting them together would have stripped ``no-store`` from the
assurance surface precisely because it is deliberately ineligible for conditional reads.

Applied as middleware, and derived from the manifest, for the same reason the ETag registry is: a
directive written by hand in a handler is a directive the next handler forgets, and a renamed route
would leave its ``no-store`` behind at the old address. The assurance surface is where that would
matter most — a stored confidential body is a disclosure, not a performance regression.

Never overwrites a header the response already carries. An error response has already declared
``no-store`` by the time it gets here, and the 304 path has declared ``no-cache``; a directive
chosen for a specific response outranks the operation's default.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.rest.route_policy import row_for_request


def directive_for(method: str, path: str) -> str | None:
    """The declared directive for a request, or None where no operation claims it.

    By method as well as path: a `PATCH` shares its path with a `GET` and answers with a body no one
    should keep, so it must not borrow the read's `no-cache`.
    """
    row = row_for_request(method, path)
    return row.cache_directive if row is not None else None


async def apply_cache_directive(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    if "cache-control" in response.headers:
        return response
    directive = directive_for(request.method, request.url.path)
    if directive is not None:
        response.headers["Cache-Control"] = directive
    return response
