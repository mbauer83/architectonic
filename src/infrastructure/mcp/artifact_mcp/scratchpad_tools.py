"""Scratchpad MCP tools — the same seven capabilities the REST surface serves.

Parity here is a property of this feature rather than of the platform: the scratchpad is the
lowest-barrier surface, so a human-only version would make the one place newcomers start the one
place agents cannot help. Both surfaces are thin adapters over `ScratchpadService`, neither reaches
past it, and `tests/architecture/test_scratchpad_surface_parity.py` holds the two sets equal.

There is still no per-note tool: the resource is the aggregate on both surfaces. What there is, is
one write in two shapes — `replace` sends the document, `edit` sends what changed — because sending
a hundred notes back to remove one is a cost a canvas does not pay and an agent does.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.modeling.artifact_write import generate_entity_id
from src.application.scratchpad.document import (
    from_document,
    lift_to_document,
    summary_to_document,
    to_response,
)
from src.application.scratchpad.edit import ScratchpadEdit
from src.application.scratchpad.ports import ScratchpadNotFoundError, ScratchpadVersionConflictError
from src.application.scratchpad.service import ScratchpadService
from src.domain.scratchpad import ScratchpadError
from src.infrastructure.mcp.artifact_mcp.context import resolve_repo_roots
from src.infrastructure.mcp.tool_annotations import (
    DESTRUCTIVE_LOCAL_WRITE,
    LOCAL_WRITE,
    READ_ONLY,
)
from src.infrastructure.scratchpad.bulk_write_lift import BulkWriteLiftWriter
from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository

#: Said once and attached to every tool, because the shape is the whole contract here and an agent
#: that learns it from one tool should not have to rediscover it from the next.
_AGGREGATE_NOTE = (
    "\n\nThe resource is the whole scratchpad — there is no per-note or per-link operation, here or "
    "on REST. To change one thing use scratchpad_edit, which takes a delta; to write a document you "
    "already hold whole use scratchpad_replace. Both carry the `version` you read, and a stale one "
    "is refused rather than overwriting, because a scratchpad is a document someone else may have "
    "open."
)


def _registry():  # noqa: ANN202 — the registry's own type, resolved lazily like every other use
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


def _service(repo_root: str | None) -> ScratchpadService:
    roots = resolve_repo_roots(
        repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None
    )
    return ScratchpadService(
        YamlScratchpadRepository(roots[0]), _registry(), BulkWriteLiftWriter(roots[0])
    )


def _failure(exc: Exception) -> dict[str, Any]:
    """A refusal an agent can act on: the domain's own sentence, plus what kind of problem it is.

    Kept verbatim — the messages name the offending id and say what to do next, and rewording them
    here would leave the caller with a worse sentence than the aggregate wrote.
    """
    kind = (
        "not_found" if isinstance(exc, ScratchpadNotFoundError)
        else "version_conflict" if isinstance(exc, ScratchpadVersionConflictError)
        else "refused"
    )
    return {"ok": False, "error": kind, "message": str(exc)}


def register_scratchpad_read_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="scratchpad_list",
        title="Scratchpad: List",
        description=(
            "List scratchpads with their metadata — id, name, status, version, collection and note "
            "count, never the notes themselves. Filter by `group` (the collection it lives in) or "
            "`status`." + _AGGREGATE_NOTE
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def scratchpad_list(
        *, group: str | None = None, status: str | None = None, repo_root: str | None = None
    ) -> dict[str, Any]:
        summaries = _service(repo_root).list_scratchpads(group=group, status=status)
        return {"ok": True, "scratchpads": [summary_to_document(summary) for summary in summaries]}

    @mcp.tool(
        name="scratchpad_read",
        title="Scratchpad: Read",
        description=(
            "Read one scratchpad whole: its areas (the labelled frames), notes, links, groups and "
            "the layout block holding every coordinate. Each note reports the `area` containing it, "
            "which is derived from where it sits rather than stored. A note needs only a title — "
            "`destination`, `element-type` and the rest are optional at every moment."
            + _AGGREGATE_NOTE
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def scratchpad_read(*, artifact_id: str, repo_root: str | None = None) -> dict[str, Any]:
        service = _service(repo_root)
        try:
            scratchpad = service.read(artifact_id)
            served = to_response(
                scratchpad, group=service.group_of(artifact_id), registry=_registry()
            )
            return {"ok": True, "scratchpad": served}
        except ScratchpadNotFoundError as exc:
            return _failure(exc)


_CREATE_DESCRIPTION = (
    "Create a scratchpad in `group` (the collection it lives in on disk). Seeded with four "
    "labelled frames — Vision & strategy, Portfolio, Project, Enabling — unless `seed_areas` is "
    "false. Nothing needs to be typed: a scratchpad exists to hold thinking before anything has "
    "been decided." + _AGGREGATE_NOTE
)

_REPLACE_DESCRIPTION = (
    "Replace a scratchpad whole. `scratchpad` is the document `scratchpad_read` returned, edited; "
    "`version` is the version you read it at. A mismatch is refused with `version_conflict` — "
    "reload and re-apply rather than retrying, or you will overwrite whatever moved.\n\n"
    "REMOVAL IS OMISSION: drop a note to delete it (its links go with it), drop a link to rub it "
    "out, and omit `element-type`, `domain`, `document-type` or `connection-type` — the key, not "
    "an empty string — to un-refine. Removal never retracts model content: deleting a `realized` "
    "note leaves the entity the lift created, and dropping `model-ref` is how a note stops "
    "claiming one.\n\n"
    "Invariants the aggregate enforces: every note has a title; a link's endpoints are notes of "
    "this scratchpad and not the same note; a group's members lie in one area and a note belongs "
    "to at most one group; the meta-ontology may not change while any note is typed. A violation "
    "is refused with the id at fault named."
)

_EDIT_DESCRIPTION = (
    "Change a scratchpad by saying what changed, instead of sending the whole document back. Same "
    "write as scratchpad_replace, same invariants, same `version` and the same 409 on a stale one.\n\n"
    "`remove` is {collection: [id, ...]}, `upsert` is {collection: [patch, ...]}, over the "
    "collections `areas`, `notes`, `groups`, `links`. A patch is a MERGE PATCH identified by its "
    "`id`: a key you leave out keeps its stored value, a key set to null clears it, and an id the "
    "scratchpad does not have creates the row. `layout` is {collection: {id: [x, y] or [x, y, w, h], "
    "or null to unplace}}.\n\n"
    "Removing a note takes its links, its group memberships and its placement with it. Nothing here "
    "retracts model content: deleting a `realized` note leaves the entity the lift created, and "
    "clearing `model-ref` is how a note stops claiming one."
)

_LIFT_DESCRIPTION = (
    "Lift a selection of notes — and the links among them — into ordinary model content, through "
    "the same verified write path as any other authoring. Plans unless `dry_run` is false.\n\n"
    "The answer reports four things per selection: what would be CREATED, what is SKIPPED because "
    "it already carries a model reference, what is REFUSED and why, and which links reach a note "
    "OUTSIDE the selection. A refusal blocks the whole lift — the write is one transaction.\n\n"
    "A lift NEVER writes back to the model. A note already bound or realized is skipped, never "
    "updated: re-lifting would be bidirectional sync between a sketch and a governed model, and "
    "would clobber whatever was edited there since. A second lift therefore creates only what is "
    "new, which is usually the links between notes lifted before.\n\n"
    "`targets` maps a FRAME's id to the model-project its content lands in — one target per frame, "
    "because the frames are work archetypes and a canvas routinely holds work for more than one "
    "project. A frame with no entry lands in the root model. A project is created if it does not "
    "exist; one declaring a different meta-ontology is refused rather than coerced. "
    "`version` is the version you read the scratchpad at — a committed lift records what it "
    "created on the notes, so it is a write against that version.\n\n"
    "`draw` adds a layered ArchiMate view of what was lifted, with each of the scratchpad's GROUPS "
    "as a labelled box on it. Frames map to nothing — an area is a region of the workspace, not an "
    "element of a picture. The diagram is drawn AFTER the content commits, since it can only name "
    "entities that exist, so a diagram that fails does not retract the lift."
)

_DELETE_DESCRIPTION = (
    "Delete a scratchpad and everything on it. Model content it lifted or bound is NOT touched: "
    "what a scratchpad put into the model is not the scratchpad's to retract."
)


def scratchpad_create(
    *,
    name: str,
    group: str,
    description: str = "",
    meta_ontology: str = "archimate-4",
    seed_areas: bool = True,
    repo_root: str | None = None,
) -> dict[str, Any]:
    service = _service(repo_root)
    try:
        created = service.create(
            artifact_id=generate_entity_id("SCR", name),
            name=name,
            group=group,
            description=description,
            meta_ontology=meta_ontology,
            seed_areas=seed_areas,
        )
    except (ScratchpadError, ScratchpadVersionConflictError) as exc:
        return _failure(exc)
    return {"ok": True, "scratchpad": to_response(created, group=group, registry=_registry())}


def scratchpad_replace(
    *,
    artifact_id: str,
    scratchpad: dict[str, Any],
    version: str,
    group: str | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    service = _service(repo_root)
    try:
        target_group = group or service.group_of(artifact_id)
        stored = service.replace(
            from_document(scratchpad, artifact_id=artifact_id),
            group=target_group,
            expected_version=version,
        )
    except (ScratchpadError, ScratchpadNotFoundError, ScratchpadVersionConflictError) as exc:
        return _failure(exc)
    return {"ok": True, "scratchpad": to_response(stored, group=target_group, registry=_registry())}


def scratchpad_edit(
    *,
    artifact_id: str,
    version: str,
    remove: dict[str, list[str]] | None = None,
    upsert: dict[str, list[dict[str, Any]]] | None = None,
    layout: dict[str, dict[str, list[float] | None]] | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    service = _service(repo_root)
    try:
        stored = service.edit(
            artifact_id,
            edit=ScratchpadEdit(remove=remove or {}, upsert=upsert or {}, layout=layout or {}),
            expected_version=version,
        )
        group = service.group_of(artifact_id)
    except (ScratchpadError, ScratchpadNotFoundError, ScratchpadVersionConflictError) as exc:
        return _failure(exc)
    return {"ok": True, "scratchpad": to_response(stored, group=group, registry=_registry())}


def scratchpad_lift(
    *,
    artifact_id: str,
    selection: list[str],
    version: str,
    targets: dict[str, str] | None = None,
    draw: bool = False,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, Any]:
    try:
        plan, receipt = _service(repo_root).lift(
            artifact_id,
            selection=selection,
            targets=targets or {},
            expected_version=version,
            draw=draw,
            dry_run=dry_run,
        )
    except (ScratchpadError, ScratchpadNotFoundError, ScratchpadVersionConflictError) as exc:
        return _failure(exc)
    return {"ok": True, "lift": lift_to_document(plan, receipt, dry_run=dry_run)}


def scratchpad_delete(*, artifact_id: str, repo_root: str | None = None) -> dict[str, Any]:
    try:
        _service(repo_root).delete(artifact_id)
    except ScratchpadNotFoundError as exc:
        return _failure(exc)
    return {"ok": True, "deleted": artifact_id}


def register_scratchpad_write_tools(mcp: FastMCP) -> None:
    """Through `register_mutation_tool`, not `@mcp.tool`.

    A mutating tool registered directly never reaches the write queue or the authorization gate:
    it would write outside the serialisation every other mutator observes, and no manifest row
    would classify its intent. Registration refuses without one, so this is structural rather than
    a convention to remember.
    """
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import (  # noqa: PLC0415
        register_mutation_tool,
    )

    register_mutation_tool(
        mcp,
        scratchpad_create,
        name="scratchpad_create",
        title="Scratchpad: Create",
        description=_CREATE_DESCRIPTION,
        annotations=LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        scratchpad_replace,
        name="scratchpad_replace",
        title="Scratchpad: Replace",
        description=_REPLACE_DESCRIPTION,
        # Destructive, not merely a write: the aggregate is replaced whole, so a document that
        # omits a note deletes it. MCP reserves `destructiveHint=False` for additive updates, and
        # a host warning about this one is warning about the right thing.
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        scratchpad_edit,
        name="scratchpad_edit",
        title="Scratchpad: Edit",
        description=_EDIT_DESCRIPTION,
        # Destructive: `remove` deletes, and removing a note takes its links with it. The delta
        # shape makes that visible rather than implicit, but it is the same act `replace` performs
        # by omission, so it carries the same warning.
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        scratchpad_lift,
        name="scratchpad_lift",
        title="Scratchpad: Lift",
        description=_LIFT_DESCRIPTION,
        # Additive by construction: a lift creates, and skips anything that already exists. The
        # scratchpad's own notes gain a realization reference, which is a record of what happened
        # rather than a replacement of anything.
        annotations=LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        scratchpad_delete,
        name="scratchpad_delete",
        title="Scratchpad: Delete",
        description=_DELETE_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )
