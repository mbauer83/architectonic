"""Request the REST write surface against the fixture backend, so the dark half stops being dark.

`NEVER_REQUESTED_OPERATIONS` records the operations no running server has ever answered 2xx for, and
most of them were writes. They were dark for one reason: exercising them means authoring and destroying
content, and the only backend available was serving the live self-model. The fixture removed that
reason; this walk spends it, for the writes. Five *reads* are dark for the fixture's reason as well, and
they deliberately stay out of here — see `Step`.

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
    def fixture_other_entity(self) -> str:
        return self.backend.workspace.connected_entities[1]

    @property
    def fixture_diagram(self) -> str:
        return self.backend.workspace.application_diagram

    @property
    def annotated(self) -> tuple[str, str, str]:
        """The datatype diagram, its classifier, and the attribute on it."""
        return self.backend.workspace.annotated_classifier

    @property
    def group_slug(self) -> str:
        """The walk's own group, under whatever slug it currently has.

        Read rather than fixed, because `groups_rename_group` changes the resource's address: a rename
        that left the later steps addressing the old slug would report the *rename* as working and then
        fail four steps later, on the archive.
        """
        return self.created.get("group_slug", "walk-project")

    def edge_key_of(self, diagram_id: str) -> str:
        """The PlantUML identity of an edge in this diagram, **as the product publishes it**.

        `GET /api/diagrams/{id}/context` computes `edge_key` from the rendered aliases and serves it;
        the GUI's label editor uses exactly this. So the walk asks rather than deriving it, because
        deriving it means copying the alias rule out of `_context.py` — and a copy of a rendering rule
        in a test harness is a copy that goes wrong silently, on the day the renderer changes and this
        keeps addressing an edge that is no longer drawn.

        A read inside a path builder is unusual, which is why it is a named method: the walk's steps
        are writes, and this is the one argument no write can be handed without asking first.
        """
        status, payload = _get(self.backend, f"/api/diagrams/{_q(diagram_id)}/context")
        if status != 200 or not isinstance(payload, dict):
            raise LookupError(f"diagram context for {diagram_id} answered {status}: {payload!r}")
        for connection in payload.get("connections") or []:
            key = connection.get("edge_key") if isinstance(connection, dict) else None
            if isinstance(key, str) and key:
                return key
        raise LookupError(f"diagram {diagram_id} publishes no edge to label")


@dataclass(frozen=True)
class Step:
    """One operation, the request that reaches it, and what its answer must be.

    Writes only. Five reads were dark for the fixture's reason too — a rendered image, a diagram's
    source, a datatype's classifiers — and adding them here was the obvious move and the wrong one:
    `test_the_write_walk_covers_only_write_shaped_operations` refuses it, because a register whose read
    half is partly measured by a write harness can no longer answer "how much of the read surface do the
    read suites exercise". Those five belong to the GUI conformance harness pointed at a fixture origin.
    """

    operation_id: str
    method: str
    #: Built from the context, because most write paths address something an earlier step made.
    path: Callable[[Context], str]
    body: Callable[[Context], Mapping[str, Any]] | None = None
    expect: tuple[int, ...] = (200, 201)
    #: Read from the response and remembered under this key.
    captures: str | None = None
    #: Context values this step establishes because it *asked* for them — a rename knows the new slug
    #: because it supplied it, so reading it back out of the response would be ceremony around a fact
    #: the walk already holds. Recorded only once the step answered as declared.
    records: Mapping[str, str] = field(default_factory=dict)
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
}


#: Operations the walk reaches and finds **broken**, pinned to the behaviour they currently have.
#:
#: Not `UNWALKED`: those are preconditions this fixture does not build. These are requested, reached,
#: and answered wrongly. Pinning the wrong answer is deliberate — a walk that merely failed would be
#: switched off, and one that skipped the route would report a surface that works — so the step declares
#: the defect as its expectation and *fixing* it turns this walk red, which is the signal to remove the
#: entry. Shrink-only, and it has been shrunk once already: `groups_delete_group` was pinned at 500 for
#: exactly as long as it took to read the traceback.
KNOWN_DEFECTS: Mapping[str, str] = {}


def _q(identifier: str) -> str:
    return urllib.parse.quote(identifier, safe="")


def _get(backend: FixtureBackend, path: str) -> tuple[int, Any]:
    """A plain read, for the one argument a write cannot be handed without asking the product first."""
    request = urllib.request.Request(f"{backend.base_url}{path}", method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310
            return response.status, _decoded_or_none(response.read())
    except urllib.error.HTTPError as error:
        with error:
            error.read()
        return error.code, None


STEPS: tuple[Step, ...] = (
    Step(
        "entities_create_entity", "POST", lambda _c: "/api/entities",
        lambda _c: {
            "artifact_type": "application-component",
            "name": "Walk Created Component",
            "dry_run": False,
        },
        captures="entity",
    ),
    Step(
        "entities_update_entity", "PATCH",
        lambda c: f"/api/entities/{_q(c.created['entity'])}",
        lambda _c: {"summary": "Patched by the write walk.", "dry_run": False},
    ),
    Step(
        "documents_create_document", "POST", lambda _c: "/api/documents",
        lambda _c: {"doc_type": "adr", "title": "Walk Created Decision", "body": _ADR_BODY,
                    "dry_run": False},
        captures="document",
    ),
    Step(
        "documents_update_document", "PATCH",
        lambda c: f"/api/documents/{_q(c.created['document'])}",
        lambda _c: {"title": "Walk Patched Decision", "dry_run": False},
    ),
    Step(
        # 204 as well as 200: a delete that answers "no content" is the correct answer, and my first
        # declaration of (200, 201) reported the product wrong for being right.
        "documents_delete_document", "DELETE",
        lambda c: f"/api/documents/{_q(c.created['document'])}?dry_run=false",
        expect=(200, 204), must_have_written=False,
    ),
    Step(
        "connections_create_connection", "POST", lambda _c: "/api/connections",
        lambda c: {"source_entity": c.created["entity"], "connection_type": "archimate-serving",
                   "target_entity": c.fixture_entity, "dry_run": False},
        captures="connection",
    ),
    Step(
        "connections_update_connection", "PATCH",
        lambda c: f"/api/connections/{_q(c.created['connection'])}",
        lambda _c: {"description": "Patched by the write walk.", "dry_run": False},
    ),
    Step(
        # A delta over a set-valued relation, which is why the route is a PATCH and not a PUT. The
        # *add* branch is what a walk can assert against a fixture: removing an association it did not
        # make would be asserting nothing.
        "connections_update_connection_associations", "PATCH",
        lambda c: f"/api/connections/{_q(c.created['connection'])}/associated-entities",
        lambda c: {"add_entities": [c.fixture_other_entity], "dry_run": False},
    ),
    # ── groups: the whole lifecycle, including the rename that moves the resource's address ───────
    Step(
        "groups_create_group", "POST", lambda _c: "/api/groups",
        lambda _c: {"kind": "model-project", "slug": "walk-project", "name": "Walk Project"},
        must_have_written=False,
    ),
    Step(
        "groups_update_group", "PATCH", lambda c: f"/api/groups/model-project/{c.group_slug}",
        lambda _c: {"name": "Walk Project Renamed"}, must_have_written=False,
    ),
    Step(
        # A POST with an action segment rather than a PATCH field, because a rename re-files every
        # member and changes the resource's own address. Which is why it `records` the new slug: every
        # group step after this one addresses the group where the rename left it.
        "groups_rename_group", "POST",
        lambda c: f"/api/groups/model-project/{c.group_slug}/rename",
        lambda _c: {"name": "Walk Project Moved", "new_slug": "walk-project-moved"},
        records={"group_slug": "walk-project-moved"}, must_have_written=False,
    ),
    Step(
        "groups_archive_group", "POST",
        lambda c: f"/api/groups/model-project/{c.group_slug}/archive",
        lambda _c: {}, must_have_written=False,
    ),
    Step(
        "groups_unarchive_group", "POST",
        lambda c: f"/api/groups/model-project/{c.group_slug}/unarchive",
        lambda _c: {}, must_have_written=False,
    ),
    Step(
        # Two things found here, because nothing had ever requested this operation. `confirm` is a
        # typed-slug confirmation the route requires before destroying a model-project, answering 400
        # and naming the expected value when it is missing — correct, and documented nowhere a caller
        # would look. And with `confirm` supplied it used to answer **500**: the cascade report was
        # returned verbatim under a closed response model. Fixed, and this step is what keeps it fixed.
        "groups_delete_group", "DELETE",
        lambda c: f"/api/groups/model-project/{c.group_slug}?confirm={c.group_slug}",
        expect=(200, 204), must_have_written=False,
    ),
    # ── viewpoints: create one of the walk's own, then replace it ─────────────────────────────────
    Step(
        "viewpoints_create_viewpoint", "POST", lambda _c: "/api/viewpoints",
        lambda _c: {
            "definition": {"slug": "walk-viewpoint", "version": 1, "name": "Walk Viewpoint"},
            "dry_run": False,
        },
        must_have_written=False,
    ),
    Step(
        # The body spells the slug the path addresses, and only that one: a definition naming another
        # would make URL and payload disagree about what is being written, and the route refuses it.
        # A name-only change is descriptive, so it needs no version bump — a scope or query edit would.
        "viewpoints_replace_viewpoint", "PUT", lambda _c: "/api/viewpoints/walk-viewpoint",
        lambda _c: {
            "definition": {"slug": "walk-viewpoint", "version": 1, "name": "Walk Viewpoint Replaced"},
            "dry_run": False,
        },
        must_have_written=False,
    ),
    # ── matrices: their own contract, entity ids and connection-type configs rather than PUML ─────
    Step(
        "matrices_create_matrix", "POST", lambda _c: "/api/matrices",
        lambda c: {
            "name": "Walk Connection Matrix",
            "entity_ids": [c.fixture_entity, c.fixture_other_entity],
            "conn_type_configs": [{"conn_type": "archimate-serving", "active": True}],
            "dry_run": False,
        },
        captures="matrix",
    ),
    Step(
        "matrices_replace_matrix", "PUT",
        lambda c: f"/api/matrices/{_q(c.created['matrix'])}",
        lambda c: {
            "name": "Walk Connection Matrix Replaced",
            "entity_ids": [c.fixture_entity, c.fixture_other_entity],
            "conn_type_configs": [{"conn_type": "archimate-serving", "active": True}],
            "dry_run": False,
        },
    ),
    # ── diagrams: the replace, then the two metadata patches, then the edge label ─────────────────
    Step(
        # A full replacement, so the body restates the whole selection rather than a delta. The entity
        # and connection sets are the fixture diagram's own, because what is under test is the write
        # path and not the walk's ability to invent a different diagram.
        "diagrams_replace_diagram", "PUT",
        lambda c: f"/api/diagrams/{_q(c.fixture_diagram)}",
        lambda c: {
            "diagram_type": "archimate-application",
            "name": "Fixture Application View (replaced)",
            "entity_ids": [c.fixture_entity, c.fixture_other_entity],
            "connection_ids": [c.backend.workspace.ids("connection")[0]],
            "dry_run": False,
        },
    ),
    Step(
        "diagrams_update_diagram_classifier_metadata", "PATCH",
        lambda c: (
            f"/api/diagrams/{_q(c.annotated[0])}/entities/{_q(c.annotated[1])}/metadata"
        ),
        lambda _c: {"patch": {"note": "Annotated by the write walk."}, "dry_run": False},
    ),
    Step(
        # The deepest write address in the product: diagram → classifier → attribute. `multiplicity`
        # and `note` are meta; the whitelist refuses `type`, so this cannot retype an attribute through
        # a route named for annotation.
        "diagrams_update_diagram_attribute_metadata", "PATCH",
        lambda c: (
            f"/api/diagrams/{_q(c.annotated[0])}/entities/{_q(c.annotated[1])}"
            f"/attributes/{_q(c.annotated[2])}/metadata"
        ),
        lambda _c: {
            "patch": {"multiplicity": "0..1", "note": "Annotated by the write walk."},
            "dry_run": False,
        },
    ),
    Step(
        # Last of the diagram steps, so the replace above cannot drop the override it sets. The key is
        # read from the diagram's own context route rather than derived — see `Context.edge_key_of`.
        "diagrams_set_diagram_edge_label", "PUT",
        lambda c: (
            f"/api/diagrams/{_q(c.fixture_diagram)}"
            f"/edges/{_q(c.edge_key_of(c.fixture_diagram))}/label"
        ),
        lambda _c: {"label": "labelled by the write walk", "dry_run": False},
    ),
    Step(
        "diagrams_sync_diagram_to_model", "POST",
        lambda c: f"/api/diagrams/{_q(c.fixture_diagram)}/sync",
        lambda _c: {"dry_run": False}, must_have_written=False,
    ),
    Step(
        "connections_cleanup_broken_references", "POST",
        lambda _c: "/api/connections/cleanup-broken-refs",
        lambda _c: {"dry_run": False}, must_have_written=False,
    ),
    # ── git: the engagement save, then the promotion and enterprise lifecycle it enables ──────────
    # Last on purpose, and in this order. `commit_engagement_work` refuses when there is nothing
    # uncommitted, so everything above is what it has to commit; and the enterprise branch lifecycle
    # presupposes a promotion having put something in the enterprise repository to commit.
    Step(
        "sync_save_engagement", "POST", lambda _c: "/api/sync/engagement/save",
        lambda _c: {"message": "Saved by the REST write walk", "push": True},
        must_have_written=False,
    ),
    Step(
        # File-level promotion into the fixture's own enterprise repository, and the step that gives
        # the three enterprise operations below something to be about.
        "promotion_execute_promotion", "POST", lambda _c: "/api/promote/execute",
        lambda c: {"entity_id": c.created["entity"], "dry_run": False},
        must_have_written=False,
    ),
    Step(
        "sync_save_enterprise", "POST", lambda _c: "/api/sync/enterprise/save",
        lambda _c: {"message": "Promoted by the REST write walk", "push": False},
        must_have_written=False,
    ),
    Step(
        "sync_submit_enterprise", "POST", lambda _c: "/api/sync/enterprise/submit",
        must_have_written=False,
    ),
    Step(
        # Irreversible, and it takes the submitted branch with it — which is exactly why it belongs
        # against a throwaway remote and nowhere else. `confirm` is a typed acknowledgement, not a
        # formality: without it the route answers 400 and says so.
        "sync_withdraw_enterprise", "POST", lambda _c: "/api/sync/enterprise/withdraw",
        lambda _c: {"confirm": True}, must_have_written=False,
    ),
)


def _request(backend: FixtureBackend, step: Step, path: str, body: Any) -> tuple[int, Any]:
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
            # Not every route answers JSON: `/api/diagram-images/{filename}` serves a PNG, and decoding
            # it would report a working route as broken. The status is what a reachability walk asserts.
            return response.status, _decoded_or_none(raw)
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


def _decoded_or_none(raw: bytes) -> Any:
    """The body as JSON, or ``None`` where the route legitimately answers something else."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


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
        except (LookupError, IndexError) as missing:
            # A path builder that had to *ask* the product for an argument and did not get one. Its
            # own failure, reported as its own, rather than as the request answering badly.
            failures.append(f"{step.operation_id}: could not address its target: {missing}")
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
        context.created.update(step.records)
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
