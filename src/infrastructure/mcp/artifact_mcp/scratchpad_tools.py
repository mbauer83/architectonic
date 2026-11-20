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

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ValidationError  # type: ignore[import-not-found]

from src.application.modeling.artifact_write import generate_entity_id
from src.application.scratchpad.document import (
    lift_to_document,
    summary_to_document,
)
from src.application.scratchpad.edit import ScratchpadEdit
from src.application.scratchpad.ports import ScratchpadNotFoundError, ScratchpadVersionConflictError
from src.application.scratchpad.requests import from_request_document
from src.application.scratchpad.service import ScratchpadService
from src.domain.repository.artifact_location import own_id_prefix
from src.domain.repository.groups import UNCATEGORIZED
from src.domain.scratchpad import ScratchpadError
from src.infrastructure.mcp.artifact_mcp.context import resolve_repo_roots
from src.infrastructure.mcp.artifact_mcp.scratchpad_tool_descriptions import (
    CREATE_DESCRIPTION,
    DELETE_DESCRIPTION,
    EDIT_DESCRIPTION,
    LIFT_DESCRIPTION,
    LIST_DESCRIPTION,
    READ_DESCRIPTION,
    REPLACE_DESCRIPTION,
)
from src.infrastructure.mcp.tool_annotations import (
    DESTRUCTIVE_LOCAL_WRITE,
    LOCAL_WRITE,
    READ_ONLY,
)
from src.infrastructure.rest.contracts.scratchpad_requests import (
    LayoutPatchWire,
    RemovePatchWire,
    ScratchpadDocumentWire,
    UpsertPatchWire,
)
from src.infrastructure.scratchpad.composition import scratchpad_service, served


def _root(repo_root: str | None) -> Path:
    return resolve_repo_roots(
        repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None
    )[0]


def _service(repo_root: str | None) -> ScratchpadService:
    return scratchpad_service(_root(repo_root))


def _shaped[T: BaseModel](model: type[T], sent: object) -> T:
    """The typed body, whether the caller handed over a model or the JSON object behind one.

    The annotation is what puts `destination`'s four values into the tool's published schema, so an
    agent reads them instead of discovering them by being refused. Validating here as well is not
    belt-and-braces: MCPServer builds the model when it invokes a tool, but these functions are plain
    callables that the write queue — and every test — calls directly, and a contract that only holds
    on one of its two entry paths is not a contract.

    `sent` is deliberately `object`: the parameters are annotated as the models, which is what the
    published schema is built from, and this only has to cope with the fact that a direct caller may
    hand over the mapping instead. Widening the *parameter* to a union would have put
    `anyOf[model, object]` in the schema and given the enum back to guesswork.

    A violation surfaces through `_failure` as ordinary data, because this surface answers refusals
    with something an agent can branch on rather than an exception it cannot see.
    """
    return model.model_validate(sent if sent is not None else {})


def _failure(exc: Exception) -> dict[str, Any]:
    """A refusal an agent can act on: the domain's own sentence, plus what kind of problem it is.

    Kept verbatim — the messages name the offending id and say what to do next, and rewording them
    here would leave the caller with a worse sentence than the aggregate wrote.
    """
    kind = (
        "not_found" if isinstance(exc, ScratchpadNotFoundError)
        else "version_conflict" if isinstance(exc, ScratchpadVersionConflictError)
        else "invalid_request" if isinstance(exc, ValidationError)
        else "refused"
    )
    return {"ok": False, "error": kind, "message": str(exc)}


def register_scratchpad_read_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        name="scratchpad_list",
        title="Scratchpad: List",
        description=LIST_DESCRIPTION,
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
        description=READ_DESCRIPTION,
        annotations=READ_ONLY,
        structured_output=True,
    )
    def scratchpad_read(*, artifact_id: str, repo_root: str | None = None) -> dict[str, Any]:
        service = _service(repo_root)
        try:
            scratchpad = service.read(artifact_id)
            return {"ok": True, "scratchpad": served(
                scratchpad, group=service.group_of(artifact_id), repo_root=_root(repo_root)
            )}
        except ScratchpadNotFoundError as exc:
            return _failure(exc)


def scratchpad_create(
    *,
    name: str,
    group: str = UNCATEGORIZED,
    description: str = "",
    meta_ontology: str = "archimate-4",
    seed_areas: bool = True,
    repo_root: str | None = None,
) -> dict[str, Any]:
    service = _service(repo_root)
    try:
        created = service.create(
            artifact_id=generate_entity_id(own_id_prefix("scratchpad"), name),
            name=name,
            group=group,
            description=description,
            meta_ontology=meta_ontology,
            seed_areas=seed_areas,
        )
    except (ScratchpadError, ScratchpadVersionConflictError) as exc:
        return _failure(exc)
    return {"ok": True, "scratchpad": served(created, group=group, repo_root=_root(repo_root))}


def scratchpad_replace(
    *,
    artifact_id: str,
    scratchpad: ScratchpadDocumentWire,
    version: str,
    group: str | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    service = _service(repo_root)
    try:
        target_group = group or service.group_of(artifact_id)
        stored = service.replace(
            from_request_document(
                _shaped(ScratchpadDocumentWire, scratchpad).as_document(), artifact_id=artifact_id
            ),
            group=target_group,
            expected_version=version,
        )
    except (
        ScratchpadError, ScratchpadNotFoundError, ScratchpadVersionConflictError, ValidationError
    ) as exc:
        return _failure(exc)
    return {"ok": True, "scratchpad": served(stored, group=target_group, repo_root=_root(repo_root))}


def scratchpad_edit(
    *,
    artifact_id: str,
    version: str,
    remove: RemovePatchWire | None = None,
    upsert: UpsertPatchWire | None = None,
    layout: LayoutPatchWire | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    service = _service(repo_root)
    try:
        stored = service.edit(
            artifact_id,
            edit=ScratchpadEdit(
                remove=_shaped(RemovePatchWire, remove).as_delta(),
                upsert=_shaped(UpsertPatchWire, upsert).as_delta(),
                layout=_shaped(LayoutPatchWire, layout).as_delta(),
            ),
            expected_version=version,
        )
        group = service.group_of(artifact_id)
    except (
        ScratchpadError, ScratchpadNotFoundError, ScratchpadVersionConflictError, ValidationError
    ) as exc:
        return _failure(exc)
    return {"ok": True, "scratchpad": served(stored, group=group, repo_root=_root(repo_root))}


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


def register_scratchpad_write_tools(mcp: MCPServer) -> None:
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
        description=CREATE_DESCRIPTION,
        annotations=LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        scratchpad_replace,
        name="scratchpad_replace",
        title="Scratchpad: Replace",
        description=REPLACE_DESCRIPTION,
        # Destructive, not merely a write: the aggregate is replaced whole, so a document that
        # omits a note deletes it. MCP reserves `destructive_hint=False` for additive updates, and
        # a host warning about this one is warning about the right thing.
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        scratchpad_edit,
        name="scratchpad_edit",
        title="Scratchpad: Edit",
        description=EDIT_DESCRIPTION,
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
        description=LIFT_DESCRIPTION,
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
        description=DELETE_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )
