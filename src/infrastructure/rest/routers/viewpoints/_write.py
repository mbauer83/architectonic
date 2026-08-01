"""Creating, replacing and deleting a viewpoint definition.

Split from the read/catalog endpoints when that module passed the size limit; the seam is the
persist path, which is the only part of the surface that writes the catalog file and therefore the
only part that goes through ``authorized_write``.

The delete contract is the plan's deletion convention: 204 for a committed deletion, 200 with the
plan for a dry run, and an *error* for a refusal — 409 ``viewpoint_referenced`` with the views that
still pin the slug, 403 for an enterprise/module definition this repository may not touch, 404 for
one that does not exist here. A refusal used to arrive as a 200 whose ``ok`` was false, which any
caller could forget to read.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

from src.application.viewpoints.persist_definition import (
    PersistAction,
    ViewpointPersistResult,
    delete_viewpoint_definition,
    persist_viewpoint_definition,
)
from src.application.viewpoints.registry_snapshot import build_registry_snapshot
from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
)
from src.domain.viewpoints.viewpoint_parsing import viewpoint_definition_from_mapping
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.rest.contracts.errors import (
    ApiError,
    DenialDetails,
    ErrorEnvelope,
    FieldError,
    ValidationErrorDetails,
    ViewpointReferencedDetails,
    ViewpointReferencerRef,
)
from src.infrastructure.rest.contracts.viewpoints import ViewpointPersistResponse
from src.infrastructure.rest.route_policy import reserved_segments_under
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import TAG_VIEWPOINTS, WRITE_RESPONSES
from src.infrastructure.viewpoint_declarations import (
    load_effective_viewpoint_catalog,
    load_viewpoint_catalog_file,
    write_viewpoint_catalog_file,
)

router = APIRouter()

#: Slugs no viewpoint may have, because the collection already spells them literally. Derived from
#: the manifest, so a new sibling route reserves its segment without anyone remembering to.
_RESERVED_SLUGS = reserved_segments_under("/api/viewpoints")


def _reject_reserved_slug(slug: str) -> None:
    """Refuse a slug the collection spells literally — before it becomes an unaddressable record.

    Answering 404 instead (which is what the router would otherwise produce for a *delete* of one)
    would say "no such viewpoint" and invite a caller to create it, and a viewpoint named ``pins``
    could never be read back: every request for it would resolve to the pin list.
    """
    if slug in _RESERVED_SLUGS:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "bad_request",
            f"{slug!r} is reserved by the viewpoints collection and cannot name a viewpoint",
        )


def _engagement_root():
    root = s.maybe_engagement_root()
    if root is None:
        raise HTTPException(500, "Engagement repository not initialized")
    return root


def _both_roots() -> list[Any]:
    return list(s.get_repo().repo_roots)


class ViewpointWriteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: dict[str, Any]
    dry_run: bool = True
    fork_of: str | None = None
    """Origin slug when this create is a fork (Save as…) — the persist path stamps the
    lineage server-side; a client can never assert its own provenance."""


def _persist(action: PersistAction, body: ViewpointWriteBody, *, operation_id: str) -> dict[str, Any]:
    engagement_root = _engagement_root()
    both_roots = _both_roots()
    catalogs = process_runtime_catalogs()
    merged_catalog = load_effective_viewpoint_catalog(both_roots)
    local_catalog = load_viewpoint_catalog_file(engagement_root)
    registries = build_registry_snapshot(
        catalogs,
        both_roots,
        derivation_max_hops=viewpoints_derivation_max_hops(),
        derivation_max_relationships=viewpoints_derivation_max_relationships(),
        derivation_time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
    )
    body_slug = body.definition.get("slug")
    if isinstance(body_slug, str):
        _reject_reserved_slug(body_slug)
    try:
        parsed = viewpoint_definition_from_mapping(body.definition)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # The model generation is only recorded into fork lineage — plain creates/edits
    # never need it.
    index_generation = s.get_repo().read_model_version().generation if body.fork_of is not None else None
    result = persist_viewpoint_definition(
        action,
        parsed,
        local_catalog=local_catalog,
        merged_catalog=merged_catalog,
        registries=registries,
        fork_of=body.fork_of,
        index_generation=index_generation,
    )
    if result.ok and not body.dry_run and result.catalog_to_write is not None:
        s.authorized_write(
            operation_id, write_viewpoint_catalog_file, engagement_root, result.catalog_to_write
        )
    return result.as_answer(dry_run=body.dry_run)


#: A create answers 201 and names the resource in ``Location``; a dry run created nothing and
#: answers 200 with its plan. Declared, because a status the handler can return that the document
#: does not mention is a contract no client can rely on.
_CREATE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": ViewpointPersistResponse, "description": "Dry-run plan; nothing was created"},
}

#: A committed deletion has nothing to report, so 204 carries no model — FastAPI refuses one on a
#: 204, correctly. The dry run reports its plan at 200, and a deletion blocked by referencers is a
#: 409 rather than a 200 whose ``ok`` is false.
_DELETE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": ViewpointPersistResponse, "description": "Dry-run plan; nothing was deleted"},
    409: {"model": ErrorEnvelope, "description": "Diagrams still pin this viewpoint"},
}


@router.post("/api/viewpoints", tags=[TAG_VIEWPOINTS], summary="Create a viewpoint",
    response_model=ViewpointPersistResponse, responses=_CREATE_RESPONSES,
    status_code=status.HTTP_201_CREATED)
def create_viewpoint_definition(body: ViewpointWriteBody, response: Response) -> dict[str, Any]:
    result = _persist("create", body, operation_id="viewpoints_create_viewpoint")
    # A dry run created nothing, so it cannot answer 201 or name a Location.
    if body.dry_run or not result["ok"]:
        response.status_code = status.HTTP_200_OK
    else:
        response.headers["Location"] = f"/api/viewpoints/{quote(str(result['slug']), safe='')}"
    return result


@router.put("/api/viewpoints/{slug}", tags=[TAG_VIEWPOINTS], summary="Replace a viewpoint",
    response_model=ViewpointPersistResponse, responses=WRITE_RESPONSES)
def replace_viewpoint_definition(slug: str, body: ViewpointWriteBody) -> dict[str, Any]:
    """The path names the definition to replace; the body carries the whole new definition.

    A viewpoint's slug is its *natural* key and part of the definition record, so the body
    legitimately spells it — but only the same one. A definition naming another slug would make the
    URL and the payload disagree about which viewpoint is being written, and there is no defensible
    winner, so it is refused.
    """
    body_slug = body.definition.get("slug")
    if isinstance(body_slug, str) and body_slug != slug:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_error",
            "the definition names a different viewpoint than the path addresses",
            ValidationErrorDetails(
                field_errors=[
                    FieldError(
                        field="body.definition.slug",
                        message=f"{body_slug!r} does not address {slug!r}",
                    )
                ]
            ),
        )
    return _persist("edit", body, operation_id="viewpoints_replace_viewpoint")


@router.delete("/api/viewpoints/{slug}", tags=[TAG_VIEWPOINTS], summary="Delete a viewpoint",
    response_model=None, responses=_DELETE_RESPONSES, status_code=status.HTTP_204_NO_CONTENT)
def delete_viewpoint_definition_route(
    slug: str, response: Response, dry_run: bool = False
) -> dict[str, Any] | None:
    _reject_reserved_slug(slug)
    engagement_root = _engagement_root()
    both_roots = _both_roots()
    merged_catalog = load_effective_viewpoint_catalog(both_roots)
    local_catalog = load_viewpoint_catalog_file(engagement_root)
    repo = s.get_repo()
    result = delete_viewpoint_definition(
        slug, local_catalog=local_catalog, merged_catalog=merged_catalog, read_access=repo
    )
    # A dry run reports what would happen — including the reasons it would not — as a plan.
    if dry_run:
        response.status_code = status.HTTP_200_OK
        return result.as_answer(dry_run=True)
    if not result.ok:
        raise _delete_refusal(slug, result)
    if result.catalog_to_write is not None:
        s.authorized_write(
            "viewpoints_delete_viewpoint", write_viewpoint_catalog_file, engagement_root, result.catalog_to_write
        )
    # A committed deletion has nothing to say, so it says nothing.
    return None


def _delete_refusal(slug: str, result: ViewpointPersistResult) -> ApiError:
    """The refusal a blocked deletion is, in the envelope's own vocabulary.

    A refusal used to be a 200 whose ``ok`` was false, which every caller had to remember to check
    — and the one that forgot reported a deletion that never happened. Each reason gets the status
    that describes it, and the referenced case carries the referencers so the client can link to
    them instead of re-fetching.
    """
    if result.referencers:
        return ApiError(
            status.HTTP_409_CONFLICT,
            "viewpoint_referenced",
            f"{slug!r} is still pinned by {len(result.referencers)} view(s)",
            ViewpointReferencedDetails(
                slug=slug,
                referencers=[
                    ViewpointReferencerRef(artifact_id=r.artifact_id, target_kind=r.target_kind)
                    for r in result.referencers
                ],
            ),
        )
    message = result.issues[0].message if result.issues else f"cannot delete {slug!r}"
    codes = {issue.code for issue in result.issues}
    if "read-only-definition" in codes:
        return ApiError(
            status.HTTP_403_FORBIDDEN,
            "forbidden",
            message,
            DenialDetails(reason_code="read-only-definition"),
        )
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", message)
