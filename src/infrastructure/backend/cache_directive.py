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

import re
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from src.infrastructure.rest.route_policy import ROUTE_POLICY, served_templates_for


def _pattern(template: str) -> re.Pattern[str]:
    return re.compile(
        "^"
        + "/".join(
            r"[^/]+" if segment.startswith("{") and segment.endswith("}") else re.escape(segment)
            for segment in template.split("/")
        )
        + "$"
    )


#: ``(path matcher, directive)`` for every operation the manifest gives a directive, at whichever
#: address it is served from today — legacy where a rename is still pending, canonical otherwise.
_DIRECTIVES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (_pattern(template), row.cache_directive)
    for row in ROUTE_POLICY
    for template in served_templates_for(row.operation_id)
)


def directive_for_path(path: str) -> str | None:
    """The declared directive for a request path, or None where no operation claims it."""
    for pattern, directive in _DIRECTIVES:
        if pattern.match(path):
            return directive
    return None


async def apply_cache_directive(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    if "cache-control" in response.headers:
        return response
    directive = directive_for_path(request.url.path)
    if directive is not None:
        response.headers["Cache-Control"] = directive
    return response
