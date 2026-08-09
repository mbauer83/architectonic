"""Scratchpad MCP tools — the same five capabilities the REST surface serves.

**Five, matching REST exactly**, because parity here is a property of this feature rather than of
the platform: the scratchpad is the lowest-barrier surface, so a human-only version would make the
one place newcomers start the one place agents cannot help. Both surfaces are thin adapters over
`ScratchpadService`, neither reaches past it, and
`tests/architecture/test_scratchpad_surface_parity.py` holds the two sets equal.

Both also work the same way: read the aggregate, change it, write it back whole. An agent has no
canvas, but it has the document — so there is no per-note tool, and therefore no capability an
agent has that a person does not, or the reverse.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.application.modeling.artifact_write import generate_entity_id
from src.application.scratchpad.document import from_document, summary_to_document, to_response
from src.application.scratchpad.ports import ScratchpadNotFoundError, ScratchpadVersionConflictError
from src.application.scratchpad.service import ScratchpadService
from src.domain.scratchpad import ScratchpadError
from src.infrastructure.mcp.artifact_mcp.context import resolve_repo_roots
from src.infrastructure.mcp.tool_annotations import (
    DESTRUCTIVE_LOCAL_WRITE,
    LOCAL_WRITE,
    READ_ONLY,
)
from src.infrastructure.scratchpad.yaml_repository import YamlScratchpadRepository

#: Said once and attached to every tool, because the shape is the whole contract here and an agent
#: that learns it from one tool should not have to rediscover it from the next.
_AGGREGATE_NOTE = (
    "\n\nA scratchpad is read and written WHOLE — there is no per-note or per-link operation, on "
    "this surface or on REST. To change one thing: read it, edit the returned document, and pass "
    "it back to scratchpad_replace with the `version` you read. A stale version is refused rather "
    "than overwriting, because a scratchpad is a document someone else may have open."
)


def _registry():  # noqa: ANN202 — the registry's own type, resolved lazily like every other use
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


def _service(repo_root: str | None) -> ScratchpadService:
    roots = resolve_repo_roots(
        repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None
    )
    return ScratchpadService(YamlScratchpadRepository(roots[0]))


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
    "Invariants the aggregate enforces: every note has a title; a link's endpoints are notes of "
    "this scratchpad and not the same note; a group's members lie in one area and a note belongs "
    "to at most one group; the meta-ontology may not change while any note is typed. A violation "
    "is refused with the id at fault named."
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
