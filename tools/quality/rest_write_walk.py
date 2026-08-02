"""Request the REST write surface against the fixture backend, so the dark half stops being dark.

`NEVER_REQUESTED_OPERATIONS` records 78 operations no running server has ever answered 2xx for, and 52
of those are writes. They were dark for one reason: exercising them means authoring and destroying
content, and the only backend available was serving the live self-model. The fixture removed that
reason; this walk spends it.

**Ordered, stateful and destructive on purpose.** A write surface is not a set of independent calls —
nothing can PATCH what it has not POSTed, and a DELETE has to be handed something it is allowed to
destroy. So the steps run in sequence against one backend, threading ids through a `Context`, and the
workspace is discarded afterwards.

**A step asserts its status, not its shape.** This is a reachability walk: what it establishes is that
an operation is served, reaches its handler, and answers as the manifest says. Response shape is
already asserted by `tests/architecture/test_response_contract_fitness.py` and the decoder conformance
suite, and duplicating it here would be a second place to update.

**What it must never do is pass quietly.** A 2xx that refused the write is the trap this release kept
finding — the refusal rides inside the success, as `wrote: false` with the reason in
`verification.issues`. So a mutating step fails on that, and the walk reports what the *server's own
log* says was requested rather than what the walk intended.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.quality.fixture_backend import FixtureBackend, fixture_backend  # noqa: E402

_ADR_BODY = (
    "## Context\n\nCreated by the REST write walk.\n\n"
    "## Decision\n\nExercise the operation.\n\n"
    "## Consequences\n\nNone: a later step deletes this document.\n"
)


@dataclass
class Context:
    """Ids the walk creates, so later steps can address what earlier ones made."""

    backend: FixtureBackend
    created: dict[str, str] = field(default_factory=dict)

    @property
    def fixture_entity(self) -> str:
        return self.backend.workspace.connected_entities[0]

    @property
    def fixture_diagram(self) -> str:
        return self.backend.workspace.ids("diagram")[0]


@dataclass(frozen=True)
class WriteStep:
    """One operation, the request that reaches it, and what its answer must be."""

    operation_id: str
    method: str
    #: Built from the context, because most write paths address something an earlier step made.
    path: Callable[[Context], str]
    body: Callable[[Context], Mapping[str, Any]] | None = None
    expect: tuple[int, ...] = (200, 201)
    #: Read from the response and remembered under this key.
    captures: str | None = None
    #: A mutation must report that it wrote. Off where a 2xx is legitimately not a write.
    must_have_written: bool = True


#: Operations this walk does not request, each with its reason. Shrink-only, like every other register
#: here. These are **preconditions this fixture does not build**, not oversights.
UNWALKED: Mapping[str, str] = {
    "assurance/*": (
        "every `/api/assurance/*` write needs the confidential store unlocked, which the fixture "
        "deliberately does not build — a walk that authored there would be writing analyst content "
        "into the real store. Needs a fixture *store*, which is its own slice."
    ),
    "admin/*": (
        "`/admin/api/*` needs --admin-mode, which is process-wide: one backend cannot be both. Needs a "
        "second fixture backend, which the workspace-keyed pre-start guard forbids, so it needs its "
        "own sequential run."
    ),
    "sync/*, promotion": (
        "needs a git remote to push to and an enterprise repository with history; the fixture builds "
        "neither. `tests/integration/test_promotion_cycle_end_to_end.py` covers the cycle in-process."
    ),
}


#: Operations the walk reaches and finds **broken**, pinned to the behaviour they currently have.
#:
#: Not `UNWALKED`: these are requested, reached, and answered wrongly. Pinning the wrong answer is
#: deliberate — a walk that merely failed would be switched off, and one that skipped them would report
#: a surface that works. So the step declares the defect as its expectation, and *fixing* the defect
#: fails this walk, which is the signal to remove the entry. Shrink-only, like every other register
#: here, and this is the only one whose entries are defects rather than preconditions.
KNOWN_DEFECTS: Mapping[str, str] = {
    "groups_delete_group": (
        "500 on a model-project delete. `delete_group` declares `response_model=GroupOperationResponse`, "
        "which requires `action`/`axis`/`slug` and forbids extras; the model-project path returns a "
        "cascade report instead — `{project, dry_run, applied, staged_paths, warnings, owned_deleted, "
        "foreign_connections_deleted, diagrams_updated}` — so FastAPI raises ResponseValidationError "
        "with 11 errors and every such delete answers 500. One producer, two declared shapes: the same "
        "defect class as the matrix-preview 500 and the FMEA one before it.\n\n"
        "The contract's own docstring names the fix: \"a seventh action, or an extra that is not "
        "obviously tied to one verb, is the point at which the union earns its keep\". A cascade report "
        "is not an extra field, it is a second shape. Not fixed here because a REST response model "
        "change ripples into `openapi.generated.ts`, the hand-written effect schemas and the wire-null "
        "policy tests, and that needs the full gate set to validate rather than a partial pass."
    ),
}


def _q(identifier: str) -> str:
    return urllib.parse.quote(identifier, safe="")


STEPS: tuple[WriteStep, ...] = (
    WriteStep(
        "entities_create_entity", "POST", lambda _c: "/api/entities",
        lambda _c: {
            "artifact_type": "application-component",
            "name": "Walk Created Component",
            "dry_run": False,
        },
        captures="entity",
    ),
    WriteStep(
        "entities_update_entity", "PATCH",
        lambda c: f"/api/entities/{_q(c.created['entity'])}",
        lambda _c: {"summary": "Patched by the write walk.", "dry_run": False},
    ),
    WriteStep(
        "documents_create_document", "POST", lambda _c: "/api/documents",
        lambda _c: {"doc_type": "adr", "title": "Walk Created Decision", "body": _ADR_BODY,
                    "dry_run": False},
        captures="document",
    ),
    WriteStep(
        "documents_update_document", "PATCH",
        lambda c: f"/api/documents/{_q(c.created['document'])}",
        lambda _c: {"title": "Walk Patched Decision", "dry_run": False},
    ),
    WriteStep(
        # 204 as well as 200: a delete that answers "no content" is the correct answer, and my first
        # declaration of (200, 201) reported the product wrong for being right.
        "documents_delete_document", "DELETE",
        lambda c: f"/api/documents/{_q(c.created['document'])}?dry_run=false",
        expect=(200, 204), must_have_written=False,
    ),
    WriteStep(
        "connections_create_connection", "POST", lambda _c: "/api/connections",
        lambda c: {"source_entity": c.created["entity"], "connection_type": "archimate-serving",
                   "target_entity": c.fixture_entity, "dry_run": False},
        captures="connection",
    ),
    WriteStep(
        "connections_update_connection", "PATCH",
        lambda c: f"/api/connections/{_q(c.created['connection'])}",
        lambda _c: {"description": "Patched by the write walk.", "dry_run": False},
    ),
    WriteStep(
        "groups_create_group", "POST", lambda _c: "/api/groups",
        lambda _c: {"kind": "model-project", "slug": "walk-project", "name": "Walk Project"},
        must_have_written=False,
    ),
    WriteStep(
        "groups_update_group", "PATCH", lambda _c: "/api/groups/model-project/walk-project",
        lambda _c: {"name": "Walk Project Renamed"}, must_have_written=False,
    ),
    WriteStep(
        "groups_archive_group", "POST", lambda _c: "/api/groups/model-project/walk-project/archive",
        lambda _c: {}, must_have_written=False,
    ),
    WriteStep(
        "groups_unarchive_group", "POST",
        lambda _c: "/api/groups/model-project/walk-project/unarchive",
        lambda _c: {}, must_have_written=False,
    ),
    WriteStep(
        # Two things found here, because nothing had ever requested this operation. First, `confirm` is
        # a typed-slug confirmation the route requires before destroying a model-project, answering 400
        # and naming the expected value when it is missing — correct, and undocumented anywhere a
        # caller would look. Second, with `confirm` supplied it answers **500**: see KNOWN_DEFECTS.
        "groups_delete_group", "DELETE",
        lambda _c: "/api/groups/model-project/walk-project?confirm=walk-project",
        expect=(500,), must_have_written=False,
    ),
    WriteStep(
        "diagrams_sync_diagram_to_model", "POST",
        lambda c: f"/api/diagrams/{_q(c.fixture_diagram)}/sync",
        lambda _c: {"dry_run": False}, must_have_written=False,
    ),
    WriteStep(
        "connections_cleanup_broken_references", "POST",
        lambda _c: "/api/connections/cleanup-broken-refs",
        lambda _c: {"dry_run": False}, must_have_written=False,
    ),
)


def _request(backend: FixtureBackend, step: WriteStep, path: str, body: Any) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - fixed scheme, local fixture backend
        f"{backend.base_url}{path}",
        data=data,
        method=step.method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        # `HTTPError` is itself a file object: read it, then close it. Leaving it to the collector is
        # `ResourceWarning: Implicitly cleaning up <HTTPError ...>`, which under `filterwarnings =
        # ["error"]` fails whichever test the collector happened to be inside.
        with error:
            raw = error.read()
        try:
            detail: Any = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            detail = raw.decode("utf-8", "replace")
        return error.code, detail


def walk(backend: FixtureBackend) -> tuple[list[str], list[str]]:
    """Run every step in order. Returns (operations that answered as declared, failures)."""
    context = Context(backend=backend)
    answered: list[str] = []
    failures: list[str] = []

    for step in STEPS:
        try:
            path = step.path(context)
            body = step.body(context) if step.body is not None else None
        except KeyError as missing:
            failures.append(f"{step.operation_id}: needs {missing} from a step that did not run")
            continue

        status, payload = _request(backend, step, path, body)
        if status not in step.expect:
            failures.append(f"{step.operation_id}: {step.method} {path} -> {status}, body={payload!r}")
            continue

        if step.must_have_written and isinstance(payload, dict) and payload.get("wrote") is False:
            issues = (payload.get("verification") or {}).get("issues") or payload
            failures.append(f"{step.operation_id}: answered {status} but wrote nothing: {issues!r}")
            continue

        answered.append(step.operation_id)
        if step.captures is not None:
            identifier = payload.get("artifact_id") if isinstance(payload, dict) else None
            if not isinstance(identifier, str):
                failures.append(f"{step.operation_id}: captured no artifact_id from {payload!r}")
                continue
            context.created[step.captures] = identifier

    return answered, failures


def reached_operations(backend: FixtureBackend) -> frozenset[str]:
    """What the *server's own access log* says was requested — the register's measurement, not mine.

    Deliberately not the step list: a walk that reported its own intentions would keep reporting them
    after a route moved, which is the whole failure the register exists to make visible.
    """
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

    print(f"{len(answered)} of {len(STEPS)} steps answered as declared:")
    for operation in answered:
        print(f"  {operation}")
    print(f"\n{len(reached)} manifest operations appear in the server's own log")
    print(f"not walked, by precondition: {', '.join(UNWALKED)}")
    print(f"reached but broken, pinned: {', '.join(KNOWN_DEFECTS)}")
    if failures:
        print(f"\n{len(failures)} failure(s):")
        for failure in failures:
            print(f"  {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
