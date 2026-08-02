"""Which REST operations have ever executed through the running server.

Every gate in this project answers "does the code agree with itself". None of them answers
"has the real application ever run this". The difference is measurable, because the backend
writes an access log, and diffing that log against the route-policy manifest turns "where is
the untested surface" from a hunch into a number. When this register was first taken, 73% of
the write surface had never executed outside an in-process ``TestClient`` — including
``POST /api/entities`` and all ten ``PATCH`` routes, every one of which the 0.2.0 release had
just moved to a new address *and* a new method.

The register is therefore **shrink-only**, in the same spirit as
``SOURCE_FILE_BASELINE_LIMITS``: an entry may be removed once something drives the operation
through the server, and no entry may be added. Adding one is the statement "this release ships
an address nothing has ever called", which is the precondition of every defect the browser
suite found in 0.2.0.

**Success only.** A 400 or a 404 means the route's *guard* ran and its handler did not, so a
rejected request is not evidence the operation works. Under the first, looser rule the initial
conformance run appeared to retire ``entities_allocate_identifiers`` on the strength of a request
that named an entity type the diagram kind does not own. Tightening it also *found* something:
``GET /api/assurance/analyses/{id}/completeness`` had been requested twice in 43 restarts and had
answered 409 both times.

**What this is and is not.** It is a risk map, not a coverage figure: it measures requests, and any
request counts — a browser spec, the conformance harness, a hand-run ``curl``. So it cannot prove an
operation is *tested*, only that it has never once been *exercised*, which is the weaker claim and
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
from pathlib import Path

from src.infrastructure.rest.route_policy import ROUTE_POLICY, RouteRow

#: Operations no request has ever reached through the running server. Shrink-only: remove an
#: entry when something exercises it, never add one. A new operation that would need an entry
#: has to be exercised before it is served instead.
#:
#: Taken 2026-08-02 against a log spanning 43 backend restarts since 2026-07-27.
NEVER_REQUESTED_OPERATIONS: frozenset[str] = frozenset(
    {
        # GET — 9 dark
        "assurance_list_security_components",
        "assurance_list_security_findings",
        "assurance_list_vex_assessments",
        "assurance_read_security_component",
        "assurance_read_vulnerability_impact",
        "diagrams_read_diagram_image",
        "diagrams_list_diagram_type_connection_types",
        "diagrams_list_diagram_type_entity_types",
        "diagrams_download_diagram_source",
        # POST — 27 dark
        "admin_create_connection",
        "admin_create_diagram",
        "admin_create_entity",
        "assurance_export_aibom",
        "assurance_record_gsn_publication",
        "assurance_ingest_security_signals",
        "assurance_record_vex_assessment",
        "assurance_seal_baseline",
        "assurance_create_group",
        "assurance_model_this",
        "connections_create_connection",
        "connections_cleanup_broken_references",
        "diagrams_sync_diagram_to_model",
        "documents_create_document",
        "entities_create_entity",
        "groups_create_group",
        "groups_archive_group",
        "groups_rename_group",
        "groups_unarchive_group",
        "entities_allocate_identifiers",
        "matrices_create_matrix",
        "matrices_preview_matrix",
        "promotion_execute_promotion",
        "sync_save_engagement",
        "sync_save_enterprise",
        "sync_submit_enterprise",
        "sync_withdraw_enterprise",
        # PUT — 7 dark
        "assurance_file_analysis",
        "assurance_add_participating_node",
        "assurance_assign_node_provenance",
        "diagrams_replace_diagram",
        "diagrams_set_diagram_edge_label",
        "matrices_replace_matrix",
        "viewpoints_replace_viewpoint",
        # PATCH — 10 dark
        "admin_update_entity",
        "assurance_update_analysis",
        "assurance_update_node",
        "connections_update_connection",
        "connections_update_connection_associations",
        "diagrams_update_diagram_attribute_metadata",
        "diagrams_update_diagram_classifier_metadata",
        "documents_update_document",
        "entities_update_entity",
        "groups_update_group",
        # DELETE — 11 dark
        "admin_delete_connection",
        "admin_delete_diagram",
        "admin_delete_entity",
        "assurance_remove_participating_node",
        "assurance_delete_anchor_security_snapshots",
        "assurance_delete_edge",
        "assurance_delete_group",
        "assurance_delete_security_snapshot",
        "documents_delete_document",
        "entities_delete_entity",
        "groups_delete_group",
    }
)

#: The default log location. A deployment-local artefact, not a repository one.
DEFAULT_REQUEST_LOG = Path(".arch/backend.log")

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
    best: tuple[int, str] | None = None
    for row in rows:
        if row.method != route.method:
            continue
        literals = _matches(row.template.split("/"), path_segments)
        if literals is None:
            continue
        if best is None or literals > best[0]:
            best = (literals, row.operation_id)
    return None if best is None else best[1]


def requested_operations(
    routes: Iterable[RequestedRoute], rows: Iterable[RouteRow] | None = None
) -> frozenset[str]:
    """The manifest operations a set of requests reached."""
    manifest = tuple(ROUTE_POLICY if rows is None else rows)
    reached = (operation_for(route, manifest) for route in routes)
    return frozenset(operation_id for operation_id in reached if operation_id is not None)


def never_requested_operations(
    routes: Iterable[RequestedRoute], rows: Iterable[RouteRow] | None = None
) -> frozenset[str]:
    """Declared operations that no request in ``routes`` reached."""
    manifest = tuple(ROUTE_POLICY if rows is None else rows)
    return frozenset(row.operation_id for row in manifest) - requested_operations(routes, manifest)


def read_request_log(log_path: Path | None = None) -> str | None:
    """The access log's text, or ``None`` when there is no log to read."""
    path = DEFAULT_REQUEST_LOG if log_path is None else log_path
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")
