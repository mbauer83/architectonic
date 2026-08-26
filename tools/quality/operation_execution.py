"""Which REST operations have not executed through the running server, within the recorded window.

Every gate in this project answers "does the code agree with itself". None of them answers
"has the real application ever run this". The difference is measurable, because the backend
writes an access log, and diffing that log against the route-policy manifest turns "where is
the untested surface" from a hunch into a number. When this register was first taken, 73% of
the write surface had never executed outside an in-process ``TestClient`` — including
``POST /api/entities`` and all ten ``PATCH`` routes, every one of which the 0.2.0 release had
just moved to a new address *and* a new method.

"Within the recorded window" is the honest form of the claim, and it took a deleted log to see
why. The measurement was first taken against a log spanning 43 restarts, and read as "never,
ever". Then the log — 45 MB of it — was replaced, and the same code would have reported 60-odd
dark operations from ten minutes of history: the most confident wrong answer available. A log is
**positive** evidence only. That an operation appears in it proves the operation ran; that it does
not appear proves nothing unless the log spans the period being claimed about. So the measurement
records the instant it was taken (:data:`REGISTER_TAKEN`), and the negative half of the check runs
only against a log that predates it.

**There is no longer a register of exceptions.** It was shrink-only, it reached empty on 2026-08-03,
and it stayed empty: every operation the surface serves has been requested through a running server.
An allowlist that must remain empty is a conditional in every consumer rather than a fact — the
lesson `route_policy/_pending.py` already paid for, where two ledgers that had reached empty were
removed for exactly this reason. What the gate asks now is simply whether any operation is dark.

**Success only.** A 400 or a 404 means the route's *guard* ran and its handler did not, so a
rejected request is not evidence the operation works. Under the first, looser rule the initial
conformance run appeared to retire ``entities_allocate_identifiers`` on the strength of a request
that named an entity type the diagram kind does not own. Tightening it also *found* something:
``GET /api/assurance/analyses/{id}/completeness`` had been requested twice in 43 restarts and had
answered 409 both times.

**What this is and is not.** It is a risk map, not a coverage figure: it measures requests, and any
request counts — a browser spec, the conformance harness, a hand-run ``curl``. So it cannot prove an
operation is *tested*, only that nothing in the window *exercised* it, which is the weaker claim and
the one worth gating. Shrinking an entry without adding something that keeps exercising it is
visible in the commit that shrinks it, and that visibility is the whole enforcement mechanism.

The log lives outside the repository (``.arch/backend.log``, gitignored), so the two halves of
the check have different reach. The manifest half — every registered id is a declared
operation — runs anywhere and catches a register entry stranded by a rename. The log half
needs a log, and says so rather than passing quietly when there is none.

**Why this lives under ``tools/`` and not ``src/``.** It is development-time measurement: the
product never consults it, and ``src`` is what the wheel ships. The two older policy registers
(``source_file_length``, ``line_length``) do sit in ``src``, and the only real argument for that
placement was that ``zuban`` type-checks ``src`` and nothing else — so this directory is named in
``[tool.zuban] files`` instead, which is the fix rather than the workaround. A fitness test
importing from ``tools`` is already established (``test_route_timeout_policy_agreement``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.infrastructure.rest.route_policy import RouteRow

DEFAULT_REQUEST_LOG = Path(".arch/backend.log")

#: When the surface was last measured clean — every served operation requested at least once.
#:
#: The register that recorded the exceptions is gone: it reached empty on 2026-08-03 and stayed there,
#: and an allowlist that must remain empty is a conditional in every consumer rather than a fact —
#: the lesson `route_policy/_pending.py` already paid for. What survives it is the *instant*, because
#: the negative half of the check still depends on it: a log is positive evidence only, so absence in
#: one that begins after this moment proves nothing about what ran before it started.
REGISTER_TAKEN = datetime(2026, 8, 2, 12, 40, tzinfo=UTC)

#: The timestamp uvicorn/`logging.basicConfig` puts at the head of a line: `2026-08-02 12:20:49,123`.
_LOG_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", re.MULTILINE)

#: uvicorn's access-log format: ``… "METHOD /path HTTP/1.1" 200``. Matched rather than parsed
#: line-by-line because the log interleaves application logging at several levels, and a
#: request line is recognisable by its own shape wherever it appears.
_ACCESS_LINE = re.compile(r'"(GET|POST|PUT|PATCH|DELETE) (\S+) HTTP/[0-9.]+" (\d{3})')

#: The application's own record of the same event, from `arch_backend_app._log_requests`:
#: ``HTTP request completed method=GET path=/api/stats status=200 duration_ms=1.7``.
#:
#: Both shapes are read, because the log's history spans a change of format. uvicorn's access line
#: was one of *three* written per request and carried the least — no duration — so it was dropped as
#: a second rendering of an event the application already records. A log from before that carries
#: only the uvicorn shape, and this register's negative half depends on old history remaining
#: readable, so recognising one format would have retired the evidence along with the duplication.
_COMPLETED_LINE = re.compile(
    r"HTTP request completed method=(GET|POST|PUT|PATCH|DELETE) path=(\S+) status=(\d{3})"
)

_PARAMETER_SEGMENT = re.compile(r"^\{[A-Za-z_][A-Za-z0-9_]*\}$")


@dataclass(frozen=True, slots=True)
class RequestedRoute:
    """One ``(method, path)`` a client actually sent, with its query string discarded."""

    method: str
    path: str


def log_begins_at(log_text: str) -> datetime | None:
    """The first timestamp the log carries, or ``None`` if it carries none.

    Local time, because that is what the logger writes; compared against a register epoch recorded
    the same way. Precision beyond the minute is irrelevant here — the question is whether the log
    predates the register by any margin at all.
    """
    match = _LOG_TIMESTAMP.search(log_text)
    if match is None:
        return None
    naive = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=UTC)


def covers_the_register(log_text: str, taken: datetime | None = None) -> bool:
    """Whether this log can support the claim that an operation has *never* been requested.

    Positive evidence needs no coverage: a request recorded anywhere proves the operation ran. The
    negative direction is the one that needs history, and a fresh log — after a rotation, on a new
    machine, or because someone deleted 45 MB of it — has none. Reporting 60 dark operations from a
    log that is ten minutes old would be the most confident wrong answer this module could give.
    """
    begins = log_begins_at(log_text)
    if begins is None:
        return False
    return begins <= (REGISTER_TAKEN if taken is None else taken)


def parse_requested_routes(log_text: str) -> frozenset[RequestedRoute]:
    """Every distinct ``(method, path)`` the backend's log records **answering 2xx**.

    Either shape counts — see `_COMPLETED_LINE` — because one log may hold both, written either side
    of the release that stopped rendering each request twice.

    Deduplicated on the way in: the question is *whether* an operation ran, never how often, and
    the log this was built against carries 101,389 request lines.

    Only success counts, and the distinction is the whole value of the measurement. A 400 or a 404
    means the route's *guard* ran — a validator rejected the body, an identifier resolved to
    nothing — and the handler's own work never happened. Counting those would have let the first
    conformance run retire ``entities_allocate_identifiers`` from the register on the strength of a
    request that asked for an entity type the diagram kind does not own, which is the sort of
    evidence this register exists to refuse.
    """
    return frozenset(
        RequestedRoute(method, target.split("?", 1)[0])
        for pattern in (_ACCESS_LINE, _COMPLETED_LINE)
        for method, target, status in pattern.findall(log_text)
        if status.startswith("2")
    )


def _matches(template_segments: Sequence[str], path_segments: Sequence[str]) -> int | None:
    """How many literal segments a template matches, or ``None`` if it does not match at all.

    The count is the tie-breaker between two templates that both accept one path.
    ``/api/viewpoints/pins`` and ``/api/viewpoints/{slug}`` both accept ``/api/viewpoints/pins``;
    the server matches the literal because it is registered first, so the more literal template
    is the operation that actually ran.
    """
    if len(template_segments) != len(path_segments):
        return None
    literals = 0
    for template_segment, path_segment in zip(template_segments, path_segments, strict=True):
        if _PARAMETER_SEGMENT.match(template_segment):
            if not path_segment:
                return None
            continue
        if template_segment != path_segment:
            return None
        literals += 1
    return literals


def operation_for(route: RequestedRoute, rows: Iterable[RouteRow]) -> str | None:
    """The manifest operation a concrete request reached, or ``None`` if the manifest serves none.

    ``None`` is ordinary: the log also carries the MCP mount, the static bundle and requests to
    addresses this release retired.
    """
    path_segments = route.path.split("/")
    candidates = (
        (literals, row.operation_id)
        for row in rows
        if row.method == route.method
        and (literals := _matches(row.template.split("/"), path_segments)) is not None
    )
    # Most literal segments wins, and the operation id breaks a tie — deterministic rather than
    # "whichever row the manifest happens to list first".
    best = max(candidates, default=None)
    return None if best is None else best[1]


def requested_operations(
    routes: Iterable[RequestedRoute], rows: Iterable[RouteRow]
) -> frozenset[str]:
    """The manifest operations a set of requests reached.

    ``rows`` is required, not defaulted to the process's manifest. An optional parameter falling back
    to a module-level singleton is the shape ``333c29d`` removed from eleven router modules: it reads
    as an injection seam and behaves as a service locator, so a caller that meant to supply rows and
    passed them to the wrong argument silently measures the real manifest instead.
    """
    reached = (operation_for(route, rows) for route in routes)
    return frozenset(operation_id for operation_id in reached if operation_id is not None)


def never_requested_operations(
    routes: Iterable[RequestedRoute], rows: Iterable[RouteRow]
) -> frozenset[str]:
    """Declared operations that no request in ``routes`` reached."""
    declared = tuple(rows)
    return frozenset(row.operation_id for row in declared) - requested_operations(routes, declared)


def read_request_log(log_path: Path | None = None) -> str | None:
    """The access log's text, or ``None`` when there is no log to read."""
    path = DEFAULT_REQUEST_LOG if log_path is None else log_path
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")
