"""Which operation a request addresses: its method and path matched against the manifest's templates.

Read here once for every middleware that applies a row's policy to a request — its cache directive,
its body limit — because a policy keyed on an address is only as good as the matching, and two
matchers can disagree about which row a path is. A literal segment outranks a parameter, so
`/api/icons/preview` is that operation and not an icon named `preview`.
"""

from __future__ import annotations

import functools
import re

from src.infrastructure.rest.route_policy._types import DEFAULT_MAX_BODY_BYTES, RouteRow


def template_matcher(template: str) -> re.Pattern[str]:
    """A route template as a pattern matching exactly the paths it serves."""
    return re.compile(
        "^"
        + "/".join(
            r"[^/]+" if segment.startswith("{") and segment.endswith("}") else re.escape(segment)
            for segment in template.split("/")
        )
        + "$"
    )


@functools.cache
def _matchers() -> tuple[tuple[str, re.Pattern[str], RouteRow], ...]:
    from src.infrastructure.rest.route_policy import ROUTE_POLICY  # noqa: PLC0415

    def literal_segments(row: RouteRow) -> int:
        return sum(1 for segment in row.template.split("/") if segment and not segment.startswith("{"))

    ordered = sorted(ROUTE_POLICY, key=literal_segments, reverse=True)
    return tuple((row.method, template_matcher(row.template), row) for row in ordered)


def row_for_request(method: str, path: str) -> RouteRow | None:
    """The row of the operation *method* *path* addresses, or None where no operation claims it."""
    return next(
        (row for verb, pattern, row in _matchers() if verb == method.upper() and pattern.match(path)), None,
    )


def body_limit_for(method: str, path: str) -> int:
    """The largest body the addressed operation reads; the default where it names none or none claims it."""
    row = row_for_request(method, path)
    return row.max_body_bytes if row is not None and row.max_body_bytes is not None else DEFAULT_MAX_BODY_BYTES
