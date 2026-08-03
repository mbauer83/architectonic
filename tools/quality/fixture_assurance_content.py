"""The assurance content a walk needs to have something to read, authored into the fixture store.

The confidential counterpart of the checklist in `fixture_workspace`, and there for the same reason:
21 of the 38 dark assurance operations are **reads**, and a read walk against an empty store proves
only that an empty store serves empty answers. `visibility_limited`, `max_cvss_score`,
`basis_snapshot_id` and the rest have an absent branch and a present one, and the dogfood repository
only ever showed the read walks the absent one.

**Run as a child process, not imported.** Every function below needs an unlocked store, which means a
real credential backend, which `tests/conftest.py` forbids for the whole session — see
`fixture_workspace._arch_assurance` for why that guard is right and why a child is the answer rather
than an exception to it. The child prints the ids it authored as JSON on stdout, and the parent records
them as roles; `_datatype_diagram` already works this way, for the same reason — what the product
decided is what gets recorded, not what the caller hoped.

**The application layer, not the MCP tools.** The tool wrappers add the envelope, the TLP ceiling and
the write queue, and all three are worth exercising over a real transport — which is exactly what the
declared steps in `tools/mcp/write_walk.py` and `tools/quality/rest_write_walk.py` do. This module is
the *substrate* those walks read against, so it takes the shortest honest path to content and leaves
the transport claims to the walks that exist to make them. Nothing here is faked into the database:
every row goes through the same use-case a tool would call.

**Nothing here asserts a count.** The walks that read this content assert invariants — a level appears
once, an entry is labelled and non-empty — because authoring one more node is the product working.
What this module guarantees is that each *kind* of thing exists, and it says so by publishing a role.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: The BOM the security signal surface is given. Two components and a dependency edge between them, so
#: the graph reads have something with a shape rather than a single node — copied in spirit from
#: `tests/assurance/test_signal_ingest_bundle.py`, which is where the shape is already pinned.
_BOM: dict[str, Any] = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "serialNumber": "urn:uuid:fixture-0000-0000-0000-000000000001",
    "version": 1,
    "metadata": {"component": {"bom-ref": "root", "name": "fixture-app", "version": "1.0"}},
    "components": [
        {
            "bom-ref": "direct",
            "name": "requests",
            "version": "2.31.0",
            "purl": "pkg:pypi/requests@2.31.0",
        },
        {
            "bom-ref": "indirect",
            "name": "urllib3",
            "version": "1.26.0",
            "purl": "pkg:pypi/urllib3@1.26.0",
        },
    ],
    "dependencies": [
        {"ref": "root", "dependsOn": ["direct"]},
        {"ref": "direct", "dependsOn": ["indirect"]},
    ],
}

#: One advisory against the transitive component, so `vulnerability_impact` has a real path to walk
#: (root → direct → indirect) rather than a single-hop one that cannot distinguish depth.
#:
#: **An OSV record, not a flat mapping.** `acquisition_from_records` matches a record to components
#: through `affected[].package`, and a record it cannot match becomes an *unmatched record* rather than
#: an error — so the first version of this, which carried a top-level `purl`, produced a snapshot with
#: components and no findings. Every security read still answered 200, over nothing, and the only reason
#: it surfaced at all is that `vulnerability_impact` answers 404 for an identifier the store never
#: registered. That is the shape of trap this whole exercise is about: the *status* was right.
_ADVISORY: dict[str, Any] = {
    "id": "CVE-2024-FIXTURE",
    "affected": [{
        "package": {"purl": "pkg:pypi/urllib3"},
        "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.26.5"}]}],
    }],
    "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"}],
    "summary": "A fixture advisory. Not a real vulnerability in a real component.",
}

#: The purl the advisory is *about*, versionless as OSV writes it. Kept beside the record rather than
#: parsed out of it, because the component match is on package identity and the fixture needs to say
#: which component it expects the finding to land on.
_ADVISORY_PACKAGE_PURL = "pkg:pypi/urllib3"


def _ok(result: object, what: str) -> dict[str, Any]:
    """The payload of a successful mutation, failing loudly on the refusals that wear a success.

    An assurance mutation reports its refusal by *type* — `MutationLocked`, `MutationRejected`,
    `MutationIllegalPair` — and the tool layer turns that into a 200 carrying `ok: false`. A generator
    that only caught exceptions would build an empty store and report success, which is the failure
    mode this whole fixture exists to make impossible.
    """
    payload = getattr(result, "payload", None)
    if payload is None:
        raise RuntimeError(f"fixture assurance: {what} was refused: {type(result).__name__} {result!r}")
    return dict(payload)


def author(anchor: str) -> dict[str, list[str]]:
    """Author the checklist into the store this environment resolves. Returns roles to ids.

    `anchor` is an entity id from the fixture repository, supplied by the caller that authored it. It
    has to resolve: `ingest_supplied_bom` reads it to attach the snapshot, and a `register_arch_ref`
    to an id nothing resolves stores a dangling reference that every join silently drops. Passed in
    rather than re-derived from the index, because the workspace that minted it already knows it —
    and a second derivation is a second thing that can disagree.
    """
    from src.application.assurance import analysis as analysis_uc
    from src.application.assurance import grouping as grouping_uc
    from src.application.assurance import mutations
    from src.infrastructure.assurance.edge_legality import legal_connection_types
    from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context

    ctx = get_assurance_context()
    if not ctx.is_available():
        raise RuntimeError(
            "fixture assurance: the store is not available in this child. Either the activation "
            "policy is not 'persistent' or the activation gate is missing — see "
            "fixture_workspace._build_assurance_store."
        )
    store, archive = ctx.store, ctx.archive
    roles: dict[str, list[str]] = {}

    def record(role: str, identifier: str) -> str:
        roles.setdefault(role, []).append(identifier)
        return identifier

    # ── A group, and one analysis filed into it against one that is not ───────────────────────────
    # Filing and content are separate gestures in the store, so the read surface has to be able to
    # answer both "what is in this group" and "what is filed nowhere" — which needs one of each.
    group = record("assurance_group", _ok(
        grouping_uc.create_group(store, archive, name="Fixture Filing", description="Disposable."),
        "group",
    )["group_id"])

    filed = record("assurance_filed_analysis", _ok(
        analysis_uc.create_analysis(
            store, archive, name="Fixture STPA", method="STPA", status="draft", tlp="TLP:WHITE",
        ),
        "STPA analysis",
    )["analysis_id"])
    _ok(grouping_uc.file_analysis(store, archive, analysis_id=filed, group_id=group), "filing")

    unfiled = record("assurance_analysis", _ok(
        analysis_uc.create_analysis(
            store, archive, name="Fixture FMEA", method="FMEA", status="draft", tlp="TLP:WHITE",
        ),
        "FMEA analysis",
    )["analysis_id"])

    # ── Nodes: every optional field present, then none of them ────────────────────────────────────
    hazard = record("assurance_hazard_node", _ok(
        mutations.create_node(
            store, archive,
            node_type="hazard", name="Fixture Hazard", analysis_id=filed,
            status="draft", tlp="TLP:WHITE",
            concern_class="safety",
            content_text="A hazard authored so the populated branch of every optional field is read.",
            attributes={"fixture": True},
        ),
        "hazard",
    )["node_id"])

    bare = record("assurance_bare_node", _ok(
        mutations.create_node(store, archive, node_type="loss", name="Fixture Loss", analysis_id=filed),
        "loss",
    )["node_id"])

    # A failure mode with a *guideword*, because the guideword is the matrix column it lands in. Read
    # from `FAILURE_GUIDEWORD_SLUGS` rather than named, for the reason the severity value is: the
    # ordered set is the domain's and a copy here would be a second one.
    failure_mode = record("assurance_failure_mode", _ok(
        mutations.create_node(
            store, archive,
            node_type="failure-mode", name="Fixture Failure Mode", analysis_id=unfiled,
            failure_type=_failure_guideword(),
        ),
        "failure mode",
    )["node_id"])

    # A node awaiting an architecture binding, which is what model-and-bind is *for*. Both the tool and
    # the route refuse anything else: "model-and-bind only applies to nodes with
    # binding_status='unbound-pending'". A control-structure-node because that is the type the
    # control-structure notation draws with a `[?]` marker while it waits — so this is the subject the
    # feature was built around rather than whichever node was nearest.
    record("assurance_bindable_node", _ok(
        mutations.create_node(
            store, archive,
            node_type="control-structure-node", name="Fixture Unbound Controller",
            analysis_id=filed, binding_status="unbound-pending",
        ),
        "bindable control-structure node",
    )["node_id"])

    # A *second* control-structure node, already bound, because it is what puts a row in the FMEA
    # matrix. `candidates` nominates an element only from a `binds-to` ref whose node is a
    # control-structure node — the failure mode's own ref fills a *cell* in that row and cannot create
    # one. So the matrix needs both refs, pointing at the same element, and this is the pair.
    #
    # Separate from `bindable_node` on purpose: that one exists to be handed to model-and-bind, which
    # refuses anything not `unbound-pending`, and binding it here would take the walk's subject away.
    controller = record("assurance_bound_node", _ok(
        mutations.create_node(
            store, archive,
            node_type="control-structure-node", name="Fixture Bound Controller",
            analysis_id=unfiled, binding_status="bound",
        ),
        "bound control-structure node",
    )["node_id"])

    # ── An edge, whose type the ontology chooses rather than this file ─────────────────────────────
    # Asking `legal_connection_types` for the pair is the difference between a fixture that survives an
    # ontology change and one that fails with an illegal-pair refusal nobody expects. It also means
    # this module states no vocabulary of its own.
    legal = sorted(legal_connection_types("hazard", "loss"))
    if not legal:
        raise RuntimeError("fixture assurance: the ontology permits no hazard→loss connection type")
    record("assurance_edge", _ok(
        mutations.add_edge(
            store, archive,
            source_id=hazard, target_id=bare, conn_type=legal[0],
            legal_connection_types=legal_connection_types,
        ),
        f"edge {legal[0]}",
    )["edge_id"])
    record("assurance_edge_conn_type", legal[0])

    # ── A reference into the architecture repository ───────────────────────────────────────────────
    # `register_arch_ref` canonicalises the id and stores it without checking that it resolves, so the
    # id has to be a real fixture entity for the *join* to mean anything: a read that shows the ref
    # against the entity is what proves the surface works, and a dangling ref would pass the write and
    # prove nothing.
    record("assurance_arch_ref_entity", anchor)
    # Two `binds-to` refs onto the *same* element, which together are what make an FMEA matrix cell
    # exist. The controller's ref nominates the element as a row (`candidates` accepts only
    # control-structure nodes); the failure mode's ref places it in that row, at the column its
    # guideword names. Either one alone answers `rows: [], count: 0` — a cheerful 200 over nothing, and
    # what made `assurance_set_fmea_factor` refuse for want of a basis digest that could not exist. The
    # risk register is the same projection, so it was empty for the same reason.
    for node_id, why in ((controller, "the controller, which nominates the row"),
                         (failure_mode, "the failure mode, which fills the cell")):
        _ok(
            mutations.register_arch_ref(
                store, archive,
                assurance_node_id=node_id, arch_artifact_id=anchor, ref_type="binds-to",
            ),
            f"binds-to arch ref for {why}",
        )
    _ok(
        mutations.register_arch_ref(
            store, archive,
            assurance_node_id=hazard, arch_artifact_id=anchor, ref_type="evidenced-by-artifact",
        ),
        "arch ref",
    )

    # ── Security signals, so the AIBOM and vulnerability reads have a component to answer about ────
    record("assurance_security_anchor", anchor)
    snapshot = record("assurance_security_snapshot", _ingest_signals(ctx, anchor))
    # The canonical id as the *store* registered it, not `_ADVISORY["id"]`. Vulnerability identifiers
    # come in aliases — CVE, GHSA, OSV — that the store merges onto one canonical row, so the id an
    # impact read is addressed by is the store's answer and not the one supplied. Reading it back is
    # also what proves the advisory matched a component at all: an unmatched record is not an error,
    # and this is where that silence stops.
    record("assurance_vulnerability", _canonical_vulnerability(ctx, snapshot))
    # Two identifiers for one component, and they are not interchangeable — which is the distinction
    # `_signals_routes.security_component` exists to make. `SCM@…` is the id this system minted and is
    # what *addresses* the resource; the purl identifies a package in a vocabulary another standard
    # owns, and is what a VEX assessment is keyed by. Both are read back from the store rather than
    # reconstructed from `_BOM`, which would be this file guessing at a normalisation the product owns.
    component_id, purl = _snapshot_component(ctx, snapshot)
    record("assurance_security_component", component_id)
    record("assurance_security_component_purl", purl)

    # ── One FMEA judgement, pinned to the basis the model currently presents ───────────────────────
    record("assurance_fmea_factor", _record_fmea_factor(store, archive, failure_mode))

    return roles


def _ingest_signals(ctx: Any, anchor: str) -> str:
    """Ingest the BOM and its advisory, and report the snapshot the store now holds.

    Loud on anything but an activated or replayed outcome. The first version of this returned `""` for
    every other outcome so a fixture would still build where signals are disabled — which quietly
    produced a workspace whose eight security reads had nothing to answer about, reported as
    `snapshot = None` and nothing else. A precondition that cannot be met has to say so here, where
    the reason is still in hand, rather than eight steps later as an empty list.
    """
    from src.infrastructure.assurance.signal_ingest import ingest_supplied_bom

    result = ingest_supplied_bom(
        anchor,
        _BOM,
        records=[_ADVISORY],
        snapshot_store=ctx.snapshot_store,
        request_id="fixture-ingest-1",
        source="fixture",
    )
    snapshot = getattr(result, "snapshot_id", None)
    if not isinstance(snapshot, str) or not snapshot:
        raise RuntimeError(
            f"fixture assurance: the security signals were not ingested: "
            f"{type(result).__name__} {result!r}"
        )
    return snapshot


def _failure_guideword() -> str:
    """A guideword from the domain's own ordered set — the matrix column this failure mode lands in.

    `FAILURE_GUIDEWORDS` is the matrix's column order and the order an analyst is walked through, so
    taking the first is taking the one an analyst meets first, and naming a slug here would put a copy
    of an ordered vocabulary beside the real one.
    """
    from src.domain.assurance.failure_modes import FAILURE_GUIDEWORD_SLUGS

    if not FAILURE_GUIDEWORD_SLUGS:
        raise RuntimeError("fixture assurance: the domain declares no failure guidewords")
    return FAILURE_GUIDEWORD_SLUGS[0]


def _canonical_vulnerability(ctx: Any, snapshot: str) -> str:
    """The canonical vulnerability id the snapshot's findings carry.

    Loud when there are no findings, which is the whole reason this function exists rather than a
    literal. `acquisition_from_records` matches advisories to components through
    `affected[].package`, and a record it cannot match is recorded as *unmatched* rather than refused —
    so a malformed advisory produces a snapshot with components, no findings, and eight security reads
    that all answer 200 over nothing. The status is right and the fixture is empty.
    """
    findings = ctx.snapshot_store.list_snapshot_findings(snapshot)
    if not findings:
        raise RuntimeError(
            f"fixture assurance: snapshot {snapshot} holds no findings, so every security read would "
            f"answer 200 over nothing. The advisory did not match a component — check that "
            f"`_ADVISORY` is an OSV record whose affected[].package purl is "
            f"{_ADVISORY_PACKAGE_PURL!r} and that a component carries that package."
        )
    for row in findings:
        canonical = str(row.get("canonical_vulnerability_id") or "")
        if canonical:
            return canonical
    raise RuntimeError(
        f"fixture assurance: findings in {snapshot} carry no canonical vulnerability id: {findings}"
    )


def _snapshot_component(ctx: Any, snapshot: str) -> tuple[str, str]:
    """The `SCM@…` id and the purl of the component the advisory is about, as the store holds them.

    The component with the finding against it, so a VEX assessment recorded for it is about something
    that actually has one — the pairing the VEX reads join on. Matched on purl rather than taken by
    position, because which row comes back first is the store's business and not a fact to depend on.
    """
    components = ctx.snapshot_store.list_snapshot_components(snapshot)
    if not components:
        raise RuntimeError(f"fixture assurance: snapshot {snapshot} holds no components")
    for row in components:
        purl = str(row.get("purl") or "")
        component_id = str(row.get("component_id") or "")
        # The row's purl carries the version; the advisory's package identity does not. Matching on
        # the prefix is the same identity comparison `_identity_of_purl` makes.
        if purl.startswith(f"{_ADVISORY_PACKAGE_PURL}@") and component_id:
            return component_id, purl
    raise RuntimeError(
        f"fixture assurance: no component in {snapshot} carries the advisory's package "
        f"{_ADVISORY_PACKAGE_PURL!r}; the advisory would have nothing to be about. Components: "
        f"{[(row.get('component_id'), row.get('purl')) for row in components]}"
    )


def _record_fmea_factor(store: Any, archive: Any, failure_mode: str) -> str:
    """One severity judgement against the digest the model currently derives.

    The digest is **read, not invented**. `record_factor_assessment` refuses a blank one, and a wrong
    one is worse than a refusal: the judgement would be filed against a basis that never existed, so
    it could never be retired by the model moving — which is the entire purpose of pinning it. So this
    asks `derive_factors` for the current digest, exactly as the matrix read does.
    """
    from src.application.assurance.fmea_derivation import derive_factors
    from src.application.assurance.fmea_factors import RecordFactorRequest, record_factor_assessment
    from src.domain.assurance.fmea_factors import FACTOR_SCALES, SEVERITY

    # The value comes from the scale the domain declares, not from a literal here. A judgement is one
    # of an ordered set of words — "'3' is not a member of the severity scale" is how this file learned
    # that — and naming a member would put this fixture's copy of the vocabulary next to the real one.
    scale = FACTOR_SCALES[SEVERITY]
    value = scale[len(scale) // 2]

    nodes = list(store.list_nodes())
    edges = list(store.list_edges())
    derived = derive_factors(failure_mode, nodes=nodes, edges=edges)
    digest = derived.digests.get(SEVERITY, "")
    if not digest:
        raise RuntimeError(
            "fixture assurance: no severity basis digest was derived, so a judgement pinned to it "
            "would be refused — see fmea_factors.record_factor_assessment"
        )

    result = record_factor_assessment(
        RecordFactorRequest(
            node_id=failure_mode,
            factor=SEVERITY,
            basis_digest=digest,
            value=value,
            justification="A fixture judgement, recorded so the matrix and risk register read a cell.",
            author="fixture-generator",
        ),
        store=store,
        archive=archive,
    )
    if not hasattr(result, "revision"):
        raise RuntimeError(f"fixture assurance: the factor was not recorded: {result!r}")
    return failure_mode


def main(argv: list[str] | None = None) -> int:
    """Author into the store this process's environment resolves, and print the roles as JSON."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--anchor", required=True,
        help="an entity id from the fixture repository to anchor references and signals to",
    )
    args = parser.parse_args(argv)

    print(json.dumps(author(args.anchor)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
