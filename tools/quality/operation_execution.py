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
not appear proves nothing unless the log spans the period being claimed about. So the register
records the instant it was taken (:data:`REGISTER_TAKEN`), and the negative half of the check runs
only against a log that predates it.

The register is **shrink-only**, in the same spirit as ``SOURCE_FILE_BASELINE_LIMITS``: an entry
may be removed once something drives the operation through the server, and no entry may be added.
Adding one is the statement "this release ships an address nothing in the window has called",
which is the precondition of every defect the browser suite found in 0.2.0.

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

#: Operations no request has ever reached through the running server. Shrink-only: remove an
#: entry when something exercises it, never add one. A new operation that would need an entry
#: has to be exercised before it is served instead.
#:
#: Taken 2026-08-02 against a window containing one full `npm run conformance` and one full
#: `npm run test:e2e` — 461 distinct successful routes, 79 of 166 operations untouched.
#:
#: **Re-cut 2026-08-02 to 64.** Coverage stopped coming from one process: `tools/quality/
#: rest_write_walk.py` requests fourteen write operations against its *own* fixture backend, on its own
#: port, so `.arch/backend.log` cannot contain them however often the walk runs. The window is now that
#: log **plus** the walk's — `never_requested_operations.py --log` is repeatable for exactly this — and
#: the fitness function subtracts the walk's declared steps, whose evidence is
#: `tests/tools/test_rest_write_walk.py` asserting each one appears in the fixture backend's log.
#:
#: That window is deliberately *reproducible*, which the first take was not. The first was measured
#: against 43 restarts' worth of accumulated history including every hand-run `curl`, so it flattered
#: the read surface (9 dark GETs where an honest automated window has 27) and could never be
#: reproduced by running anything. This one is a statement about what the **suites** exercise, which
#: is the thing worth gating: re-taking it means running those two suites, not remembering what was
#: poked at over five days.
NEVER_REQUESTED_OPERATIONS: frozenset[str] = frozenset(
    {
        "admin_create_connection",
        "admin_create_diagram",
        "admin_create_entity",
        "admin_delete_connection",
        "admin_delete_diagram",
        "admin_delete_entity",
        "admin_update_entity",
        "assurance_add_participating_node",
        "assurance_assign_node_provenance",
        "assurance_create_group",
        "assurance_delete_anchor_security_snapshots",
        "assurance_delete_edge",
        "assurance_delete_group",
        "assurance_delete_security_snapshot",
        "assurance_export_aibom",
        "assurance_file_analysis",
        "assurance_ingest_security_signals",
        "assurance_list_aibom_roles",
        "assurance_list_analysis_nodes",
        "assurance_list_gsn_publications",
        "assurance_list_participating_nodes",
        "assurance_list_security_components",
        "assurance_list_security_findings",
        "assurance_list_vex_assessments",
        "assurance_model_this",
        "assurance_read_aibom_coverage",
        "assurance_read_analysis",
        "assurance_read_analysis_completeness",
        "assurance_read_coverage",
        "assurance_read_edge_catalog",
        "assurance_read_gsn_draft",
        "assurance_read_gsn_render",
        "assurance_read_risk_register",
        "assurance_read_security_component",
        "assurance_read_security_stats",
        "assurance_read_stats",
        "assurance_read_vulnerability_impact",
        "assurance_record_gsn_publication",
        "assurance_record_vex_assessment",
        "assurance_remove_participating_node",
        "assurance_scan_aibom_candidates",
        "assurance_seal_baseline",
        "assurance_search_nodes",
        "assurance_update_analysis",
        "assurance_update_node",
        "connections_update_connection_associations",
        "diagrams_download_diagram_source",
        "diagrams_list_diagram_type_connection_types",
        "diagrams_list_diagram_type_entity_types",
        "diagrams_read_diagram_image",
        "diagrams_replace_diagram",
        "diagrams_set_diagram_edge_label",
        "diagrams_update_diagram_attribute_metadata",
        "diagrams_update_diagram_classifier_metadata",
        "documents_read_document_schemata",
        "groups_rename_group",
        "matrices_create_matrix",
        "matrices_replace_matrix",
        "promotion_execute_promotion",
        "sync_save_engagement",
        "sync_save_enterprise",
        "sync_submit_enterprise",
        "sync_withdraw_enterprise",
        "viewpoints_replace_viewpoint",
    }
)

#: The default log location. A deployment-local artefact, not a repository one.
#:
#: Authoritative only while the backend was started the way that owns this file — `arch-backend
#: --daemon` (or `--restart --daemon`). Launched any other way, with the caller capturing stdout, the
#: server logs *there* and this file stops growing while still looking like a record. That is how a
#: 45 MB log came to be 30 minutes stale during a run, which is the failure this module's coverage
#: check exists to refuse.
DEFAULT_REQUEST_LOG = Path(".arch/backend.log")

#: When the register below was last taken. The log half of the check is only sound where the log
#: *spans* this instant: a log that begins afterwards has no way to show that an operation was
#: requested before it started, so absence in it is not evidence of never.
REGISTER_TAKEN = datetime(2026, 8, 2, 12, 40, tzinfo=UTC)

#: The timestamp uvicorn/`logging.basicConfig` puts at the head of a line: `2026-08-02 12:20:49,123`.
_LOG_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", re.MULTILINE)

#: uvicorn's access-log format: ``… "METHOD /path HTTP/1.1" 200``. Matched rather than parsed
#: line-by-line because the log interleaves application logging at several levels, and a
#: request line is recognisable by its own shape wherever it appears.
_ACCESS_LINE = re.compile(r'"(GET|POST|PUT|PATCH|DELETE) (\S+) HTTP/[0-9.]+" (\d{3})')

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
    """Every distinct ``(method, path)`` an access log records **answering 2xx**.

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
        for method, target, status in _ACCESS_LINE.findall(log_text)
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
