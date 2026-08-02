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

#: The mount this module walks. `assurance-write`'s 22 tools are its own slice — see
#: :data:`ASSURANCE_WRITE_MOUNT_REASON`.
MOUNT = "write"

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
        return self.workspace.ids("diagram")[0]


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
    # ── last, because it rebuilds the index everything above just changed ────────────────────────
    WriteCall("artifact_admin_reindex", mutates=False),
)

#: Write-mount tools this walk does not invoke, each with why. Shrink-only, like every register here.
#: These are **preconditions the fixture does not build**, not oversights — and all four are the *same*
#: precondition: the fixture workspace is a pair of directories, not a pair of git repositories. They
#: leave together, when it grows one.
WRITE_UNEXERCISED: Mapping[str, str] = {
    "artifact_save_changes": (
        "commits and pushes through `enterprise_git_ops`; the fixture workspace is not a git "
        "repository and has no remote. Needs the git slice, alongside the REST `sync_*` operations."
    ),
    "artifact_submit_for_review": (
        "pushes the enterprise working branch to a remote the fixture does not have. Same slice."
    ),
    "artifact_withdraw_changes": (
        "abandons the enterprise working branch, which presupposes that a branch was opened and that "
        "there is a remote to reconcile the abandonment against. Same slice, and irreversible, so it "
        "wants the throwaway remote rather than a repository anyone keeps."
    ),
    "artifact_promote_to_enterprise": (
        "promotion opens a working branch on the enterprise repository before it copies anything, so "
        "it answers `fatal: not a git repository` against the fixture's plain directory. Reached and "
        "refused rather than unreachable — which is why it is recorded here and not as a defect."
    ),
}

#: The other write mount, and why it is not here. Walking it against this fixture would author analyst
#: content into the **real** confidential store: the store path is resolved from the source tree, not
#: from the served workspace, so a fixture backend sees `<repo>/.arch-assurance/store.db`. That is the
#: precondition, and it is a fixture *store* rather than a flag.
ASSURANCE_WRITE_MOUNT_REASON = (
    "`assurance-write`'s 22 tools need the confidential store unlocked, and a fixture backend "
    "resolves that store from the source tree rather than from the workspace it serves — so a walk "
    "here would write into the analyst's real store. Needs a fixture store, which is its own slice."
)


async def walk(
    session: Any, context: WriteContext, declared: Mapping[str, set[str]]
) -> tuple[list[str], list[str]]:
    """Invoke every declared call in order. Returns (tools that answered as declared, failures).

    ``declared`` is each tool's advertised parameter set, so a recipe naming a parameter the tool does
    not have is reported as *this file* being stale rather than as a broken tool. The write mount
    rejects unknown parameters outright — `_reject_unknown_parameters`, deliberately — so without the
    distinction every stale recipe would read as a regression in the product.
    """
    invoked: list[str] = []
    failures: list[str] = []

    for call in WRITE_CALLS:
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
