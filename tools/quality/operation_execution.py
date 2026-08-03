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
#: **Re-cut 2026-08-02 to 43.** The admin slice: `--admin-mode` is process-wide, so the enterprise write
#: surface needed a *second, sequential* fixture backend rather than more steps in the first walk — which
#: is exactly what `UNWALKED` said, and what `fixture_backend(admin_mode=True)` plus the cross-process
#: lock now provide. All seven `/admin/api/*` writes go green, and the first run that reached them found
#: `admin_create_diagram` answering 200 with `wrote: false` on *every* non-empty selection: the route
#: discarded the used-id lists `resolve_diagram_selection` hands it, and the verifier refuses a body that
#: draws what the frontmatter does not name. An operation nothing had ever requested, broken for as long
#: as it had existed, found by requesting it once.
#:
#: `UNWALKED` is down to one entry, `assurance/*`, waiting on a fixture store.
#:
#: **Re-cut 2026-08-02 to 50.** The git slice: the fixture workspace became a pair of real git
#: repositories, each with a throwaway bare remote beside it, and the five operations that were waiting
#: on "needs a git remote to push to and an enterprise repository with history" went green on the first
#: run — save, promote, save-enterprise, submit, withdraw, in that order, because each presupposes the
#: one before. POST went 15 dark to 10. The same slice emptied the MCP write mount's own register: all
#: 25 tools on `/mcp/write` are now invoked over the transport.
#:
#: **Re-cut 2026-08-02 to 55.** Ten more steps in the write walk, and the two worst surfaces stopped
#: being the worst: PUT went 7-of-8 dark to 3-of-8, PATCH 6-of-10 to 3-of-10, and every entry remaining
#: in either is assurance or admin. What unblocked the two deepest was giving the fixture a datatype
#: diagram with a classifier carrying an attribute — the three-level address
#: `/api/diagrams/{id}/entities/{clf}/attributes/{a}/metadata` needs, and the likeliest reason nothing
#: had ever requested it.
#:
#: **Re-cut 2026-08-03 to 38.** The reads no client drives now have a walk of their own,
#: `tools/quality/rest_read_walk.py`, against the same fixture backend — separate from the write walks
#: because `test_the_write_walk_covers_only_write_shaped_operations` refuses reads there and is right to.
#: Five operations, each with its reason printed by the walk: two reachable only by a user gesture (an
#: `<img>` src the inline-SVG surface never takes, a download-menu click no spec makes) and three with no
#: consumer at all, kept because each answers something no other address does.
#:
#: The palette pair got more than coverage. `artifact_authoring_guidance(diagram_type=…)` answered
#: accepted *domains* and left an agent to derive the type list; both transports now read
#: `application.modeling.diagram_kind_palette`, so the tool answers the same lists the route serves and
#: `tests/application/test_diagram_kind_palette_parity.py` holds them together. No new MCP tool and no
#: new parameter — the tool already took `diagram_type`; what changed is what it answers.
#:
#: **Two entries left on 2026-08-03 for an uncomfortable reason, recorded because the register is only
#: worth having if this is written down.** `documents_read_document_schemata` and
#: `diagrams_list_diagram_type_entity_types` were requested by a hand-run `curl` against the dev backend
#: while somebody was working out what they were *for*. That put them in the log, which made the
#: register's claim about them false, and `test_the_register_holds_nothing_that_has_since_been_requested`
#: said so. The gate is right and the register shrank.
#:
#: What it does **not** mean is that they are covered. This module's own docstring says any request
#: counts — "a browser spec, the conformance harness, a hand-run `curl`" — and that is deliberate,
#: because the register measures reachability rather than testing. But a diagnostic `curl` is not
#: repeatable evidence, so the honest reading is: these two have **no consumer**, still, and the fact now
#: lives in this prose instead of in a register entry that can never be re-added. Anyone measuring the
#: read surface from here should treat those two as unmeasured rather than as covered.
#:
#: The lesson is about method, not about these routes: investigating a dark operation against a logged
#: backend consumes the evidence that it was dark. Probe a fixture backend instead — its log is its own.
#:
#: Three *reads* remain dark, and the note that used to say they
#: "belong to the GUI conformance harness once it is pointed at a fixture origin" was **wrong**. That
#: harness is complete now: its unexercised register is empty and every port method is driven. These
#: five stayed dark through a full browser suite, a full read conformance run and both write walks, so
#: they are not waiting on a harness. Two have since been consumed by the `curl` described above; the
#: three groupings below are what they *are*, whether or not the register still lists them, and none of
#: the three is a gate's problem:
#:
#: * `diagrams_download_diagram_source` — `DownloadMenu.vue` builds the URL and a *user click* fetches
#:   it. Reachable only by a gesture no spec makes; a download-assertion spec would cover it.
#: * `diagrams_read_diagram_image` — `diagramImageUrl` builds it for an `<img>` src, and the diagram
#:   surface renders inline SVG instead, so the image path is a fallback nothing currently takes.
#: * `documents_read_document_schemata`, `diagrams_list_diagram_type_entity_types`,
#:   `diagrams_list_diagram_type_connection_types` — **no consumer anywhere in the repository**. Not the
#:   GUI (only the generated OpenAPI types mention them), not the CLI, not MCP. Three GETs the product
#:   serves and nothing asks for. Whether that is dead surface to retire or a client that was never
#:   written is a product decision, not a measurement one, which is why they are recorded rather than
#:   quietly covered by a harness reaching for them on nobody's behalf.
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
#:
#: ── Empty as of 2026-08-03 ────────────────────────────────────────────────────────────────────────
#:
#: The last 38 entries were the whole `/api/assurance/*` surface — 17 writes and 21 reads — and they
#: were dark for one precondition rather than for 38 reasons: every one needs the confidential store
#: unlocked, and the only unlocked store on this machine holds the analyst's real evidence. A walk
#: could not have them without either writing into that evidence or reading it and asserting against
#: it. `fixture_workspace` builds a disposable store now, so they are requested by
#: `rest_write_walk.py` (17 steps) and `rest_read_walk.py` (21 steps) against a fixture backend.
#:
#: **Cut from the walk logs alone**, which is the whole 38: no dogfood log was consulted, so nothing
#: here rests on what a developer happened to click. That matters because the two entries retired on
#: 2026-08-02 *were* retired by a hand-run `curl`, and the note above says why that is not coverage.
#: Provenance, not filename, is the test — `.arch/backend.log` is legitimate evidence when what filled
#: it was the browser suite and the read conformance run, and is not when it was a diagnostic probe.
#:
#: The 38 did not come free, and what they cost is the argument for having done it. Covering them found
#: a product defect — `anchor_reader_for` resolved the architecture model from `Path.cwd()`, so signal
#: ingest refused every anchor in any deployment whose working directory was not the workspace, which
#: both existing ingest suites hid by monkeypatching the resolution away. It also found two ways this
#: harness was lying: `_answers.refusal` could not see the assurance mount's `{"error": …}` refusal
#: shape, so a refused FMEA write reported itself green; and the FMEA matrix answered
#: `rows: [], count: 0` for want of a `binds-to` reference, so a judgement had no basis digest to pin
#: itself to while every read still answered 200. None of the three was visible to a status assertion.
NEVER_REQUESTED_OPERATIONS: frozenset[str] = frozenset()

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
