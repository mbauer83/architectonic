"""Invoke every write-mount MCP tool over the transport, against a disposable fixture repository.

`WRITE_MOUNTS` in `conformance.py` recorded 47 tools nobody had ever called through JSON-RPC — the
whole write half of the MCP surface — for one reason: the only backend available was serving the live
self-model, and exercising a write tool means authoring and destroying content. The fixture removed
that reason. This spends it for the `write` mount's 25 tools.

**Only against a fixture backend, and that is structural rather than a warning.** The recipes address
the workspace through `FixtureBackend.workspace`, which exists only when this module built the backend
itself. There is no `--url` for the write walk: a `--url` is exactly how somebody would point it at
`:8000` once, and once is enough to delete real content.

**Ordered and stateful.** Nothing can edit what it has not created, and a delete has to be handed
something it may destroy. So the calls run in declared order — not the mount's listing order, which is
alphabetical and would try to delete before it created — threading ids through a `WriteContext`.

**A refusal arrives inside a success.** These tools answer 200 with `wrote: false` and the reason in
`verification.issues`; the viewpoint and sync tools answer `ok: false`. `_answers.refusal` reads both,
and a call declared as a mutation fails on either. Without that this walk would report 25 tools covered
having written nothing — which is the failure mode the fixture generator itself hit first.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.mcp._answers import decoded, refusal, rows_of, text_of  # noqa: E402
from tools.quality.fixture_workspace import FixtureWorkspace  # noqa: E402

#: The repository write mount.
MOUNT = "write"

#: The confidential store's write mount. Walked against the fixture *store* the fixture workspace now
#: builds — see `fixture_workspace._build_assurance_store`. Until that existed there was nowhere to
#: put these 22 tools' writes except the analyst's real store, which is why they were dark.
ASSURANCE_MOUNT = "assurance-write"

#: How long one tool gets to answer. Generous — a write reindexes, and this runs on a developer
#: machine under load — and **bounded**, which is the point: the first run of this walk hung
#: indefinitely on a tool whose response never completed, and an unbounded gate that hangs is
#: indistinguishable from one that is slow. A timeout turns "I waited eight minutes and learned
#: nothing" into a named tool and a line number.
CALL_TIMEOUT_SECONDS = 120

_ADR_BODY = (
    "## Context\n\nCreated by the MCP write walk.\n\n"
    "## Decision\n\nInvoke the tool over the transport.\n\n"
    "## Consequences\n\nNone: a later call deletes this document.\n"
)


@dataclass
class WriteContext:
    """The fixture's content, and what the walk has made so far.

    `created` is keyed by role rather than by tool, because two calls to one tool make two different
    things and a later call wants the one it means — the same reason the fixture workspace publishes
    `unreferenced_entity` as a property instead of an index into a list.
    """

    workspace: FixtureWorkspace
    created: dict[str, str] = field(default_factory=dict)
    #: The basis digest the FMEA matrix currently derives for the fixture's failure mode.
    #:
    #: Read from the *read* mount before this walk starts, never composed here. A judgement carries the
    #: picture of the model it was made against, `record_factor_assessment` refuses a blank digest, and
    #: a wrong one is worse than a refusal — the judgement would be pinned to a basis that never
    #: existed, so nothing could ever retire it, which is the whole purpose of pinning it.
    fmea_basis_digest: str = ""

    @property
    def fixture_entity(self) -> str:
        """An entity the fixture authored, with a connection already on it."""
        return self.workspace.connected_entities[0]

    @property
    def spare_entity(self) -> str:
        """The other end of that connection — a second real entity to associate and connect to."""
        return self.workspace.connected_entities[1]

    @property
    def doomed_entity(self) -> str:
        """An entity nothing references, so a delete has something it is allowed to destroy."""
        return self.workspace.unreferenced_entity

    @property
    def fixture_diagram(self) -> str:
        return self.workspace.application_diagram


@dataclass(frozen=True)
class Capture:
    """An id to take out of one call's answer, so a later call can address it.

    ``read`` locates it, rather than the walk assuming a top-level ``artifact_id``: the batch tools
    answer a list of per-item results, and one call can publish two ids — `artifact_bulk_write` yields
    both the operation it registered and the artifact it made. Declaring them as data is what keeps
    `walk` free of per-tool special cases.
    """

    key: str
    read: Callable[[object], str | None]


@dataclass(frozen=True)
class WriteCall:
    """One tool, the arguments to invoke it with, and what its answer must be."""

    tool: str
    #: Built from the context, because most write recipes address something an earlier call made.
    arguments: Callable[[WriteContext], Mapping[str, Any]] = field(default=lambda _c: {})
    captures: tuple[Capture, ...] = ()
    #: A mutation must not report a refusal. Off where this tool is a read wearing write clothing, or
    #: where a `false` is the correct answer to what was asked.
    mutates: bool = True


def _artifact_id(payload: object) -> str | None:
    if isinstance(payload, Mapping):
        identifier = payload.get("artifact_id")
        return identifier if isinstance(identifier, str) else None
    return None


def _first_row_artifact_id(payload: object) -> str | None:
    rows = rows_of(payload)
    return _artifact_id(rows[0]) if rows else None


def _first_row_operation_id(payload: object) -> str | None:
    rows = rows_of(payload)
    if not rows:
        return None
    identifier = rows[0].get("operation_id")
    return identifier if isinstance(identifier, str) else None


#: What to invoke each `write`-mount tool with, in the order the surface allows. Every tool the mount
#: lists is either here or in :data:`WRITE_UNEXERCISED` with a reason, and the walk asserts that — so a
#: newly registered write tool cannot arrive uninvoked and unnoticed.
WRITE_CALLS: tuple[WriteCall, ...] = (
    # ── reads on a write mount. Registered rather than skipped: they are listed here, so a caller
    #    that asked "is every tool on this mount reachable" must be answered about them too.
    WriteCall("artifact_help", mutates=False),
    WriteCall("artifact_authoring_guidance", lambda _c: {"target": "entity"}, mutates=False),
    # ── entities: create, edit, and delete the one the fixture left unreferenced ─────────────────
    WriteCall(
        "artifact_create_entity",
        lambda _c: {
            "artifact_type": "application-component",
            "name": "MCP Walk Created Component",
            "summary": "Authored through the write mount's own transport.",
            "dry_run": False,
        },
        captures=(Capture("entity", _artifact_id),),
    ),
    WriteCall(
        "artifact_edit_entity",
        lambda c: {
            "artifact_id": c.created["entity"],
            "summary": "Edited through the write mount's own transport.",
            "dry_run": False,
        },
    ),
    # ── connections: onto the entity just made, then edited, then re-associated ──────────────────
    WriteCall(
        "artifact_add_connection",
        lambda c: {
            "source_entity": c.created["entity"],
            "connection_type": "archimate-serving",
            "target_entity": c.fixture_entity,
            "description": "Authored by the MCP write walk.",
            "dry_run": False,
        },
        captures=(Capture("connection", _artifact_id),),
    ),
    WriteCall(
        "artifact_edit_connection",
        lambda c: {
            "source_entity": c.created["entity"],
            "target_entity": c.fixture_entity,
            "connection_type": "archimate-serving",
            "operation": "update",
            "description": "Edited by the MCP write walk.",
            "dry_run": False,
        },
    ),
    WriteCall(
        "artifact_edit_connection_associations",
        lambda c: {
            "source_entity": c.created["entity"],
            "target_entity": c.fixture_entity,
            "connection_type": "archimate-serving",
            "add_entities": [c.spare_entity],
            "dry_run": False,
        },
    ),
    # ── documents: the full create → edit → delete round trip ────────────────────────────────────
    WriteCall(
        "artifact_create_document",
        lambda _c: {
            "doc_type": "adr",
            "title": "MCP Walk Created Decision",
            "body": _ADR_BODY,
            "dry_run": False,
        },
        captures=(Capture("document", _artifact_id),),
    ),
    WriteCall(
        "artifact_edit_document",
        lambda c: {
            "artifact_id": c.created["document"],
            "title": "MCP Walk Edited Decision",
            "dry_run": False,
        },
    ),
    WriteCall(
        "artifact_delete_document",
        lambda c: {"artifact_id": c.created["document"], "dry_run": False},
    ),
    # ── diagrams and matrices ────────────────────────────────────────────────────────────────────
    WriteCall(
        "artifact_create_diagram",
        lambda c: {
            "diagram_type": "archimate-application",
            "name": "MCP Walk Application View",
            "entity_ids": [c.created["entity"], c.fixture_entity],
            "dry_run": False,
        },
        captures=(Capture("diagram", _artifact_id),),
    ),
    WriteCall(
        "artifact_edit_diagram",
        lambda c: {
            "artifact_id": c.created["diagram"],
            "name": "MCP Walk Application View (edited)",
            "dry_run": False,
        },
    ),
    WriteCall(
        "artifact_delete_diagram",
        lambda c: {"artifact_id": c.created["diagram"], "dry_run": False},
    ),
    WriteCall(
        "artifact_create_matrix",
        lambda c: {
            "name": "MCP Walk Connection Matrix",
            "matrix_markdown": (
                "| Source | Target | Type |\n|---|---|---|\n"
                f"| {c.fixture_entity} | {c.spare_entity} | serving |\n"
            ),
            "dry_run": False,
        },
        captures=(Capture("matrix", _artifact_id),),
    ),
    # ── viewpoints: a definition of its own, so nothing shipped is edited ────────────────────────
    WriteCall(
        "artifact_viewpoint",
        lambda _c: {
            "action": "create",
            "definition": {"slug": "mcp-walk-viewpoint", "version": 1, "name": "MCP Walk Viewpoint"},
            "dry_run": False,
        },
    ),
    # ── groups: create, then destroy with the typed confirmation the product requires ────────────
    WriteCall(
        "artifact_group",
        lambda _c: {
            "kind": "model-project",
            "action": "create",
            "target": "mcp-walk-project",
            "name": "MCP Walk Project",
            "dry_run": False,
        },
        mutates=False,
    ),
    # ── the batch surface, and the operation register it writes into ─────────────────────────────
    WriteCall(
        "artifact_bulk_write",
        lambda _c: {
            "items": [
                {
                    "op": "create_entity",
                    "artifact_type": "application-component",
                    "name": "MCP Walk Bulk Component",
                }
            ],
            "dry_run": False,
        },
        captures=(
            Capture("bulk_operation", _first_row_operation_id),
            # The artifact the batch made, so the batch delete below has something of its own making
            # to remove rather than borrowing content another call depends on.
            Capture("bulk_entity", _first_row_artifact_id),
        ),
    ),
    WriteCall(
        # The only caller of the operation register that reads it back, and the only way to invoke it
        # with an id that exists: `artifact_bulk_write` above registered one. A literal would either
        # be invented (and raise) or copied from a log (and rot).
        "artifact_get_operation",
        lambda c: {"operation_id": c.created["bulk_operation"]},
        mutates=False,
    ),
    WriteCall(
        "artifact_bulk_delete",
        lambda c: {
            "items": [{"op": "delete_entity", "artifact_id": c.created["bulk_entity"]}],
            "dry_run": False,
        },
    ),
    # ── the destructive singles, last, against content nothing else needs ────────────────────────
    WriteCall(
        "artifact_delete_entity",
        lambda c: {"artifact_id": c.doomed_entity, "dry_run": False},
    ),
    # ── git: promote, then the save/submit/withdraw lifecycle that presupposes it ─────────────────
    # After everything above, in this order, and for the same reasons the REST walk's git steps are:
    # `artifact_save_changes` refuses when there is nothing uncommitted, so the calls above are what it
    # commits; and the enterprise branch lifecycle presupposes a promotion having put something in the
    # enterprise repository to commit.
    WriteCall(
        "artifact_promote_to_enterprise",
        lambda c: {
            "entity_id": c.created["entity"],
            "enterprise_root": str(c.workspace.enterprise_root),
            "dry_run": False,
        },
        mutates=False,
    ),
    WriteCall(
        "artifact_save_changes",
        lambda _c: {"message": "Saved by the MCP write walk", "target": "engagement", "push": True},
        mutates=False,
    ),
    WriteCall(
        # The same tool against the other repository. Two calls rather than one, because the two
        # targets take different paths — the enterprise branch is opened here and pushed below — and a
        # walk that only exercised the default would report the tool covered on half its contract.
        "artifact_save_changes",
        lambda _c: {"message": "Promoted by the MCP write walk", "target": "enterprise"},
        mutates=False,
    ),
    WriteCall("artifact_submit_for_review", mutates=False),
    WriteCall(
        # Irreversible, and it takes the branch just submitted with it. Safe only because the remote is
        # a bare repository the fixture made and throws away.
        "artifact_withdraw_changes",
        lambda _c: {"confirm": True},
        mutates=False,
    ),
    # ── last, because it rebuilds the index everything above just changed ────────────────────────
    WriteCall("artifact_admin_reindex", mutates=False),
)

#: Write-mount tools this walk does not invoke, each with why. Shrink-only, like every register here.
#:
#: **Empty as of 2026-08-02.** It held four, all on one precondition: the fixture workspace was a pair of
#: directories rather than a pair of git repositories, so save, submit, withdraw and promote had no
#: branch, no upstream and — for promotion, which opens a working branch before it copies anything —
#: not even a `.git`. They left together, when the fixture grew both, each with a throwaway bare remote
#: beside it. All 25 tools on this mount are now invoked over the transport.
WRITE_UNEXERCISED: Mapping[str, str] = {}

#: Which FMEA factor the assurance walk judges, named once because the read and the write must agree.
#:
#: A basis digest is *per factor*, so a judgement filed against another factor's digest is refused —
#: and the refusal arrives as a bare `{"error": …}`, which is a shape `_answers.refusal` had to learn.
#: `detectability` because it is derived, so the matrix carries a digest for it whatever the analysis
#: holds; `occurrence` has no derived value and its basis is whatever a rationale cited, which the
#: fixture does not author.
ASSURANCE_FMEA_FACTOR = "detectability"

#: The BOM the walk ingests. Small on purpose: what is being exercised is the transport and the
#: anchoring, not the parser, which `tests/assurance/test_sbom_parser.py` covers at length.
_WALK_BOM: Mapping[str, Any] = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "serialNumber": "urn:uuid:mcp-walk-0000-0000-0000-000000000002",
    "version": 1,
    "metadata": {"component": {"bom-ref": "root", "name": "walk-app", "version": "1.0"}},
    "components": [
        {"bom-ref": "one", "name": "jinja2", "version": "3.1.2", "purl": "pkg:pypi/jinja2@3.1.2"},
    ],
    "dependencies": [{"ref": "root", "dependsOn": ["one"]}],
}


def _node_id(payload: object) -> str | None:
    if isinstance(payload, Mapping):
        identifier = payload.get("node_id")
        return identifier if isinstance(identifier, str) else None
    return None


def _keyed(key: str) -> Callable[[object], str | None]:
    """Read one top-level string out of an answer. The assurance envelope names its own ids."""
    def _read(payload: object) -> str | None:
        if isinstance(payload, Mapping):
            value = payload.get(key)
            return value if isinstance(value, str) else None
        return None
    return _read


#: Every tool the `assurance-write` mount lists, in an order where each has what it needs.
#:
#: The confidential counterpart of `WRITE_CALLS`, and ordered for the same reason: nothing can edit
#: what it has not created, a delete needs something it is allowed to destroy, and the deletes come
#: last so the things they destroy were useful first. Three calls are worth reading twice:
#:
#: * `assurance_set_fmea_factor` takes its basis digest from the context, which read it off the *read*
#:   mount before this walk began. Inventing one would file a judgement against a basis that never
#:   existed.
#: * `assurance_model_this` is a two-repository write and "never atomic" by its own comment: it creates
#:   an architecture entity and then binds it. So it writes into the fixture *repository* as well, and
#:   it is placed after everything that counts entities there.
#: * `assurance_assign_provenance` re-asserts the analysis the node already records. That is the
#:   idempotent case the tool documents, and the only one reachable here: the tool exists to repair
#:   nodes authored before provenance was mandatory, and the write path cannot produce one.
ASSURANCE_WRITE_CALLS: tuple[WriteCall, ...] = (
    # ── an analysis of its own, so nothing below edits the fixture's ──────────────────────────────
    WriteCall(
        "assurance_create_analysis",
        lambda _c: {"name": "MCP Walk STPA", "method": "STPA"},
        captures=(Capture("analysis", _keyed("analysis_id")),),
    ),
    WriteCall(
        "assurance_update_analysis",
        lambda c: {"analysis_id": c.created["analysis"], "name": "MCP Walk STPA (edited)"},
    ),
    # ── filing: a group, then the analysis into it ────────────────────────────────────────────────
    WriteCall(
        "assurance_create_group",
        lambda _c: {"name": "MCP Walk Group", "description": "Authored over the transport."},
        captures=(Capture("group", _keyed("group_id")),),
    ),
    WriteCall(
        "assurance_file_analysis",
        lambda c: {"analysis_id": c.created["analysis"], "group_id": c.created["group"]},
    ),
    # ── a node, edited, and drawn into the analysis ───────────────────────────────────────────────
    WriteCall(
        "assurance_create_node",
        lambda c: {
            "analysis_id": c.created["analysis"],
            "node_type": "hazard",
            "name": "MCP Walk Hazard",
            "content_text": "Authored through the assurance write mount's own transport.",
        },
        captures=(Capture("node", _node_id),),
    ),
    WriteCall(
        "assurance_edit_node",
        lambda c: {"node_id": c.created["node"], "name": "MCP Walk Hazard (edited)"},
    ),
    WriteCall(
        "assurance_assign_provenance",
        lambda c: {"node_id": c.created["node"], "analysis_id": c.created["analysis"]},
    ),
    # ── an edge to a node the fixture authored, then removed again ────────────────────────────────
    # The connection type is the fixture's, which took it from the ontology rather than naming one.
    WriteCall(
        "assurance_add_edge",
        lambda c: {
            "source_id": c.created["node"],
            "target_id": c.workspace.assurance.bare_node,
            "conn_type": c.workspace.assurance.edge_conn_type,
        },
        captures=(Capture("edge", _keyed("edge_id")),),
    ),
    WriteCall("assurance_delete_edge", lambda c: {"edge_id": c.created["edge"]}),
    # ── membership: one method borrowing another's node, then giving it back ──────────────────────
    WriteCall(
        "assurance_add_analysis_member",
        lambda c: {
            "analysis_id": c.created["analysis"],
            "node_id": c.workspace.assurance.bare_node,
        },
    ),
    WriteCall(
        "assurance_remove_analysis_member",
        lambda c: {
            "analysis_id": c.created["analysis"],
            "node_id": c.workspace.assurance.bare_node,
        },
    ),
    # ── the one-way reference into the architecture repository ────────────────────────────────────
    WriteCall(
        "assurance_register_arch_ref",
        lambda c: {
            "assurance_node_id": c.created["node"],
            "arch_artifact_id": c.workspace.assurance.security_anchor,
            "ref_type": "evidenced-by-artifact",
        },
    ),
    # ── a judgement, pinned to the basis the read mount reported ──────────────────────────────────
    WriteCall(
        "assurance_set_fmea_factor",
        lambda c: {
            "node_id": c.workspace.assurance.failure_mode,
            # The factor and the digest have to agree: a digest is per factor, so judging one factor
            # against another's basis is a refusal. `conformance.FMEA_WALK_FACTOR` is the single name
            # both the read and this write use.
            "factor": ASSURANCE_FMEA_FACTOR,
            "value": "moderate",
            "basis_digest": c.fmea_basis_digest,
            "justification": "Recorded by the MCP write walk against the digest the matrix reported.",
            "author": "mcp-write-walk",
        },
    ),
    # ── security signals: ingested, then the snapshot removed ─────────────────────────────────────
    WriteCall(
        "assurance_ingest_security_signals",
        lambda c: {
            "anchor_entity_id": c.workspace.assurance.security_anchor,
            "bom": dict(_WALK_BOM),
            "request_id": "mcp-write-walk-1",
            "source": "mcp-write-walk",
        },
        captures=(Capture("snapshot", _keyed("snapshot_id")),),
    ),
    WriteCall(
        "assurance_delete_security_snapshot",
        lambda c: {"snapshot_id": c.created["snapshot"]},
    ),
    # ── the reconciliation and preflight reads that live on a write mount ─────────────────────────
    WriteCall(
        "assurance_reconcile_aibom",
        lambda _c: {
            "discovered_components": [{"name": "jinja2", "version": "3.1.2"}],
            "modeled_components": [],
        },
        mutates=False,
    ),
    WriteCall(
        "assurance_promotion_preflight",
        lambda c: {"node_ids": [c.created["node"]]},
        mutates=False,
    ),
    # ── model-and-bind: writes an entity into the repository, then binds it ───────────────────────
    WriteCall(
        # The fixture's unbound-pending control-structure node, not the hazard this walk created: both
        # transports refuse anything whose binding status is not `unbound-pending`, and a plain create
        # leaves it `unset`. This mount always answers a *task spec* rather than binding — no
        # architecture-write port here, by separation of duties — so what it exercises is the proposal
        # path, and the REST route next door exercises the direct bind.
        "assurance_model_this",
        lambda c: {
            "assurance_node_id": c.workspace.assurance.bindable_node,
            "suggested_arch_type": "application-component",
            "suggested_name": "MCP Walk Bound Component",
        },
        mutates=False,
    ),
    # ── a baseline over what the walk has built ───────────────────────────────────────────────────
    WriteCall(
        "assurance_seal_baseline",
        lambda c: {"analysis_id": c.created["analysis"], "notes": "Sealed by the MCP write walk."},
    ),
    # ── the deletes, last, each destroying something this walk made ───────────────────────────────
    WriteCall("assurance_delete_node", lambda c: {"node_id": c.created["node"]}),
    WriteCall("assurance_delete_analysis", lambda c: {"analysis_id": c.created["analysis"]}),
    WriteCall("assurance_delete_group", lambda c: {"group_id": c.created["group"]}),
)

#: Nothing on the assurance write mount is registered as unexercised. Kept as an empty mapping rather
#: than removed, because the listing check asks every mount the same question and an absent registry
#: would make "no exemptions" indistinguishable from "no check".
ASSURANCE_WRITE_UNEXERCISED: Mapping[str, str] = {}


async def walk(
    session: Any,
    context: WriteContext,
    declared: Mapping[str, set[str]],
    calls: tuple[WriteCall, ...] = WRITE_CALLS,
) -> tuple[list[str], list[str]]:
    """Invoke every declared call in order. Returns (tools that answered as declared, failures).

    ``declared`` is each tool's advertised parameter set, so a recipe naming a parameter the tool does
    not have is reported as *this file* being stale rather than as a broken tool. The write mount
    rejects unknown parameters outright — `_reject_unknown_parameters`, deliberately — so without the
    distinction every stale recipe would read as a regression in the product.

    ``calls`` is which mount's recipes to run. One engine for both write mounts rather than two: what
    an ordered, stateful walk has to get right — naming a call before invoking it, telling a stale
    recipe from a broken tool, refusing a mutation that reports a refusal — is the same work on either,
    and the second copy of it is the one that would quietly stop doing half of that.
    """
    invoked: list[str] = []
    failures: list[str] = []

    for call in calls:
        try:
            arguments = dict(call.arguments(context))
        except KeyError as missing:
            failures.append(f"{call.tool}: needs {missing} from a call that did not run")
            continue
        except IndexError:
            failures.append(f"{call.tool}: the fixture workspace published no id it could address")
            continue

        undeclared = sorted(set(arguments) - set(declared.get(call.tool, ())))
        if undeclared:
            failures.append(
                f"{call.tool}: RECIPE names undeclared parameter(s) {undeclared}; the tool declares "
                f"{sorted(declared.get(call.tool, ()))}"
            )
            continue

        # Named before it is invoked, not after. A destructive walk that dies mid-sequence has to say
        # which call it was inside, and a report printed at the end cannot.
        print(f"  → {call.tool}", file=sys.stderr, flush=True)
        try:
            result = await session.call_tool(
                call.tool, arguments, read_timeout_seconds=timedelta(seconds=CALL_TIMEOUT_SECONDS)
            )
        except Exception as exc:  # noqa: BLE001 - any transport error is this tool's failure
            failures.append(f"{call.tool}: TOOL raised {type(exc).__name__}: {exc}")
            continue
        if getattr(result, "isError", False):
            failures.append(f"{call.tool}: TOOL error result: {text_of(result)[:400]}")
            continue

        text = text_of(result)
        if not text.strip():
            failures.append(f"{call.tool}: TOOL empty answer")
            continue
        try:
            payload = decoded(text)
        except Exception as exc:  # noqa: BLE001 - a YAML error is the answer being undecodable
            failures.append(f"{call.tool}: TOOL answer is not YAML ({exc}): {text[:200]}")
            continue

        if call.mutates:
            # Checked before the capture, so a refused write cannot hand the next call an id that
            # names nothing. This is the check the whole module exists for.
            if (reason := refusal(payload)) is not None:
                failures.append(f"{call.tool}: answered normally but refused the write: {reason}")
                continue
            if (reason := _refused_in_any_row(payload)) is not None:
                failures.append(f"{call.tool}: a batch item refused the write: {reason}")
                continue

        invoked.append(call.tool)
        for capture in call.captures:
            identifier = capture.read(payload)
            if not isinstance(identifier, str):
                failures.append(
                    f"{call.tool}: captured no {capture.key} from {str(payload)[:300]}"
                )
                continue
            context.created[capture.key] = identifier

    return invoked, failures


def _refused_in_any_row(payload: object) -> str | None:
    """A refusal hiding one level down, in a batch tool's per-item results.

    `artifact_bulk_write` answers a list and `artifact_bulk_delete` a mapping around one: the envelope
    reports no `wrote` at all, and every item's failure is inside. So a batch whose every item was
    rejected looks, at the top level, exactly like a batch that worked.
    """
    for row in rows_of(payload):
        if (reason := refusal(row)) is not None:
            return f"{row.get('op', 'item')}: {reason}"
    return None
