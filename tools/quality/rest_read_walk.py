"""Request the REST reads that no harness reaches, against the fixture backend.

Twenty-six GETs, dark for two different reasons, and the difference is worth keeping straight.

**Five had no client at all.** They survived a full browser suite, a full read conformance run and both
write walks, and the GUI conformance register is empty with every port method driven — so nothing was
going to reach them by accident. They divide in three:

* `diagrams_read_diagram_image` and `diagrams_download_diagram_source` are reachable only by a *user
  gesture*: `diagramImageUrl` builds an `<img>` src the inline-SVG surface never takes, and
  `DownloadMenu.vue` builds a URL a click fetches. No spec makes either gesture.
* `documents_read_document_schemata` and the two `diagram-types/{t}/…` palette lists have no consumer at
  all — not the GUI, not the CLI, not MCP. Kept, because each answers something no other address does:
  the raw per-doc-type `frontmatter_schema`, and the accepted entity/connection *types* (optionally
  narrowed by viewpoint) where every neighbour gives labels, hints or domains.

**Twenty-one had a client and no harness.** The whole `/api/assurance/*` read surface: the GUI drives
nearly all of it, from `AssuranceBrowseView` to `SecurityPostureDashboard` and `VulnerabilityImpactView`,
and none of it could ever be exercised automatically because every route needs the confidential store
unlocked — and the only unlocked store on this machine holds the analyst's real evidence. A fixture
*store* is what changed, not a missing consumer. Worth stating because the GUI conformance register
reads as though this surface were covered: `UNEXERCISED` is typed over `ModelRepository`, and the
assurance surface goes through no port at all, so the register cannot see it either way.

**Its own walk, not steps in the write one.** `test_the_write_walk_covers_only_write_shaped_operations`
refuses reads there, and correctly: a register whose read half is partly measured by a write harness
cannot answer the question the read half exists to ask. That refusal is what this file is.

**A step asserts its status; the fixture guarantees its content.** This walk answers "is the operation
served, reached, and 200" — not "is the answer non-empty", which belongs to the harness that owns the
content. Worth stating because the division was tested the hard way: the fixture's advisory was first
written as a flat mapping rather than an OSV record, so it matched no component, and an unmatched record
is recorded as unmatched rather than refused. The snapshot had components and no findings, and eight
security reads all answered 200 over nothing. Only `vulnerability_impact` noticed, by 404ing on an
identifier the store had never registered. The fix belongs where it now is —
`fixture_assurance_content` refuses to publish a snapshot with no findings — because a walk that
asserted shape here would be a second place to update every time a payload moved.

**And no state to thread**, which is why this is not the write walk's engine reused. A read surface *is*
a set of independent calls — nothing here creates what a later step addresses — so the ordered, stateful
`Step`/`Context` machinery next door would be scaffolding around a loop. Two of the five need one
identifier each, and both take it from the fixture rather than from another step.

Usage:

    uv run tools/quality/rest_read_walk.py
    uv run tools/quality/rest_read_walk.py --log-out /tmp/read-walk.log
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.quality.fixture_backend import FixtureBackend, fixture_backend  # noqa: E402

#: The diagram kind the palette steps ask about. A shipped kind rather than a discovered one: what these
#: two routes answer is a property of the *ontology*, so any declared kind exercises them, and picking
#: one the fixture happens to hold would make the step depend on fixture content it does not need.
_PALETTE_DIAGRAM_TYPE = "archimate-application"


@dataclass(frozen=True)
class ReadStep:
    """One read, and how to address it.

    `path` takes the backend because two of the five are addressed by something only the served diagram
    can tell you — a rendered filename, and an id. Asking is the point: a walk that assembled either
    itself would be asserting its own guess about a naming convention.
    """

    operation_id: str
    path: Callable[[FixtureBackend], str]
    #: Why this read is dark, in one line, so the walk prints what it is covering and why nobody else did.
    because: str


def _q(identifier: str) -> str:
    return urllib.parse.quote(identifier, safe="")


def _rendered_filename(backend: FixtureBackend) -> str:
    """The image file the fixture's diagram renders to, as its own detail read reports it.

    `/api/diagram-images/{filename}` is the one route on the surface whose identity parameter is a
    *derived artefact* rather than an artifact id, so the only honest way to request it is to ask the
    diagram what it renders to.
    """
    diagram = backend.workspace.application_diagram
    status, payload = _get(backend, f"/api/diagrams/{_q(diagram)}")
    name = payload.get("rendered_filename") if isinstance(payload, dict) else None
    if status != 200 or not isinstance(name, str) or not name:
        raise LookupError(f"diagram {diagram} answered {status} with no rendered_filename")
    return name


READ_STEPS: tuple[ReadStep, ...] = (
    ReadStep(
        "diagrams_read_diagram_image",
        lambda b: f"/api/diagram-images/{_q(_rendered_filename(b))}",
        "an <img> src the inline-SVG diagram surface never takes",
    ),
    ReadStep(
        "diagrams_download_diagram_source",
        lambda b: f"/api/diagrams/{_q(b.workspace.application_diagram)}/download",
        "a DownloadMenu click no browser spec makes",
    ),
    ReadStep(
        "documents_read_document_schemata",
        lambda _b: "/api/document-schemata",
        "the raw frontmatter_schema; the GUI uses the curated /api/document-types instead",
    ),
    ReadStep(
        "diagrams_list_diagram_type_entity_types",
        lambda _b: f"/api/diagram-types/{_q(_PALETTE_DIAGRAM_TYPE)}/entity-types",
        "the authoring palette; the GUI's diagram surface searches entities rather than listing types",
    ),
    ReadStep(
        "diagrams_list_diagram_type_connection_types",
        lambda _b: f"/api/diagram-types/{_q(_PALETTE_DIAGRAM_TYPE)}/connection-types",
        "the same palette question for connection types; nothing in the repository asks it either",
    ),
    # ── the confidential store's read surface ─────────────────────────────────────────────────────
    #
    # Twenty-one reads, dark for a different reason from the five above: not that no client drives them
    # — the GUI drives nearly all of them, from `AssuranceBrowseView` to `SecurityPostureDashboard` —
    # but that no *harness* could, because every one needs the store unlocked and the only unlocked
    # store on this machine held the analyst's evidence. They read the content
    # `fixture_assurance_content` authors, which is why that checklist has one of each thing rather
    # than one of anything.
    *(
        ReadStep(operation_id, path, because)
        for operation_id, path, because in (
            # ── whole-store summaries: no identity parameter, and each answers a different question ──
            (
                "assurance_read_stats",
                lambda _b: "/api/assurance/stats",
                "the store's own totals; every GUI screen shows them and no harness had asked",
            ),
            (
                "assurance_read_coverage",
                lambda _b: "/api/assurance/coverage",
                "how much of the model the analyses reach — the dashboard's headline number",
            ),
            (
                "assurance_read_risk_register",
                lambda _b: "/api/assurance/risk-register",
                "the FMEA judgements as a register, which needs a factor assessment to be non-empty",
            ),
            (
                "assurance_read_edge_catalog",
                lambda _b: "/api/assurance/edge-catalog",
                "which connection types are legal between which node types; the authoring palette",
            ),
            (
                "assurance_search_nodes",
                lambda _b: f"/api/assurance/search?q={_q('Fixture')}",
                "the search four store backends implemented four ways before it was made one",
            ),
            (
                "assurance_read_security_stats",
                lambda _b: "/api/assurance/security-stats",
                "the security posture totals, over signals the fixture ingests",
            ),
            # ── the AIBOM trio ──────────────────────────────────────────────────────────────────────
            (
                "assurance_read_aibom_coverage",
                lambda _b: "/api/assurance/aibom/coverage",
                "how much of the AI bill of materials the model accounts for",
            ),
            (
                "assurance_list_aibom_roles",
                lambda _b: "/api/assurance/aibom/roles",
                "the roles an AI component may hold; a vocabulary read with no other address",
            ),
            (
                "assurance_scan_aibom_candidates",
                lambda _b: "/api/assurance/aibom/scan",
                "candidate AI components discovered in the model, which needs a model to scan",
            ),
            # ── one analysis, read six ways ─────────────────────────────────────────────────────────
            (
                "assurance_read_analysis",
                lambda b: f"/api/assurance/analyses/{_q(b.workspace.assurance.filed_analysis)}",
                "one analysis in detail; the wizard's own read, and filed rather than loose",
            ),
            (
                "assurance_list_analysis_nodes",
                lambda b: (
                    f"/api/assurance/analyses/{_q(b.workspace.assurance.filed_analysis)}/nodes"
                ),
                "the nodes an analysis authored, as against the ones it merely participates in",
            ),
            (
                "assurance_list_participating_nodes",
                lambda b: (
                    f"/api/assurance/analyses/{_q(b.workspace.assurance.filed_analysis)}"
                    "/participating-nodes"
                ),
                "the other half of that distinction: nodes borrowed from another method",
            ),
            (
                "assurance_read_analysis_completeness",
                lambda b: (
                    f"/api/assurance/analyses/{_q(b.workspace.assurance.filed_analysis)}/completeness"
                ),
                "what the method still wants before its argument is complete",
            ),
            (
                "assurance_read_gsn_draft",
                lambda b: (
                    f"/api/assurance/analyses/{_q(b.workspace.assurance.filed_analysis)}/gsn/draft"
                ),
                "the argument structure derived from the analysis, before anyone publishes it",
            ),
            (
                "assurance_read_gsn_render",
                lambda b: (
                    f"/api/assurance/analyses/{_q(b.workspace.assurance.filed_analysis)}/gsn/rendered"
                ),
                "that same argument as a rendered diagram, which is a second code path entirely",
            ),
            (
                "assurance_list_gsn_publications",
                lambda b: (
                    f"/api/assurance/analyses/{_q(b.workspace.assurance.filed_analysis)}"
                    "/gsn/publications"
                ),
                "what an analysis has been published to; new this release, and read by nothing yet",
            ),
            # ── the anchor's security signals ───────────────────────────────────────────────────────
            (
                "assurance_list_security_components",
                lambda b: (
                    f"/api/assurance/arch-artifacts/{_q(b.workspace.assurance.security_anchor)}"
                    "/security-components"
                ),
                "the components a snapshot attached to one entity, which needs an ingest first",
            ),
            (
                "assurance_list_security_findings",
                lambda b: (
                    f"/api/assurance/arch-artifacts/{_q(b.workspace.assurance.security_anchor)}"
                    "/security-findings"
                ),
                "the advisories against those components; the fixture ingests one transitively",
            ),
            (
                # Keyed, not a plain list: both query parameters are *required*, because a VEX
                # assessment's identity is (anchor, component, vulnerability) and asking for "the
                # assessments on this entity" is not a question the resource answers.
                "assurance_list_vex_assessments",
                lambda b: (
                    f"/api/assurance/arch-artifacts/{_q(b.workspace.assurance.security_anchor)}"
                    "/vex-assessments"
                    f"?canonical_component_id={_q(b.workspace.assurance.security_component_purl)}"
                    f"&canonical_vulnerability_id={_q(b.workspace.assurance.vulnerability)}"
                ),
                "what an analyst has said about those findings, keyed by component and advisory",
            ),
            (
                "assurance_read_security_component",
                lambda b: (
                    f"/api/assurance/security-components/"
                    f"{_q(b.workspace.assurance.security_component)}"
                ),
                "one component by its canonical id, which is the store's spelling and not the BOM's",
            ),
            (
                "assurance_read_vulnerability_impact",
                lambda b: (
                    f"/api/assurance/vulnerabilities/"
                    f"{_q(b.workspace.assurance.vulnerability)}/impact"
                ),
                "which modelled entities an advisory reaches, through the dependency graph",
            ),
        )
    ),
)


def _get(backend: FixtureBackend, path: str) -> tuple[int, Any]:
    request = urllib.request.Request(f"{backend.base_url}{path}", method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310
            return response.status, _decoded_or_none(response.read())
    except urllib.error.HTTPError as error:
        # `HTTPError` is a file object; read and close it, or the collector reports an unclosed one as a
        # `ResourceWarning` and `filterwarnings = ["error"]` fails whichever test it was inside.
        with error:
            raw = error.read()
        return error.code, _decoded_or_none(raw)


def _decoded_or_none(raw: bytes) -> Any:
    """The body as JSON, or ``None`` where the route legitimately answers something else.

    `/api/diagram-images/{filename}` serves a PNG. Decoding it would report a working route as broken,
    and a reachability walk asserts the status.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def walk(backend: FixtureBackend) -> tuple[list[str], list[str]]:
    """Request every declared read. Returns (operations that answered 200, failures)."""
    answered: list[str] = []
    failures: list[str] = []
    for step in READ_STEPS:
        try:
            path = step.path(backend)
        except LookupError as missing:
            failures.append(f"{step.operation_id}: could not address its target: {missing}")
            continue
        status, payload = _get(backend, path)
        if status != 200:
            failures.append(f"{step.operation_id}: GET {path} -> {status}, body={payload!r}")
            continue
        answered.append(step.operation_id)
    return answered, failures


def reached_operations(backend: FixtureBackend) -> frozenset[str]:
    """What the server's own access log says was requested — the register's measurement, not the walk's."""
    from src.infrastructure.rest.route_policy import ROUTE_POLICY
    from tools.quality.operation_execution import parse_requested_routes, requested_operations

    log_text = backend.log.read_text(encoding="utf-8", errors="replace")
    return requested_operations(parse_requested_routes(log_text), ROUTE_POLICY)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--keep", type=Path, default=None, help="keep the fixture workspace here")
    parser.add_argument(
        "--log-out", type=Path, default=None,
        help="copy the backend's access log here, so the operation register can read it",
    )
    args = parser.parse_args(argv)

    with fixture_backend(args.keep) as backend:
        answered, failures = walk(backend)
        reached = reached_operations(backend)
        if args.log_out is not None:
            args.log_out.write_text(
                backend.log.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
            )

    print(f"{len(answered)} of {len(READ_STEPS)} reads answered 200:")
    for step in READ_STEPS:
        mark = "ok  " if step.operation_id in answered else "MISS"
        print(f"  {mark} {step.operation_id} — {step.because}")
    print(f"\n{len(reached)} manifest operations appear in the server's own log")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for failure in failures:
            print(f"  {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
