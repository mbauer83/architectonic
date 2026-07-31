"""Admin-mode endpoints — write access to both enterprise and engagement repos.

Active only when the GUI server is started with ``--admin-mode``.  All write
operations target the enterprise repo and go through ``admin_ops.py``, which
enforces ``assert_enterprise_write_root`` at every entry point.  The MCP tool
surface is entirely separate and calls the standard write functions (which
unconditionally enforce ``assert_engagement_write_root``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._openapi import WRITE_RESPONSES, WriteResultResponse

router = APIRouter(prefix="/admin/api", tags=["admin"])


#: Every write here answers with the shared write result, so the model is declared once and the two
#: alternative statuses are declared with it. The manifest has always named this contract; the
#: decorators did not, which left seven operations counted as untyped while returning exactly the
#: shape the closed model describes.
#:
#: A create answers 201 and names the resource in ``Location``; a dry run created nothing, so it
#: answers 200 with its plan instead of claiming a resource that does not exist.
_ADMIN_CREATE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was created"},
}

#: A committed delete answers 204 with no body — FastAPI refuses a response model on one, correctly.
#: The dry-run outcome answers 200 with its plan.
_ADMIN_DELETE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was deleted"},
}


def _created(result: Any, response: Response, location: str) -> dict[str, Any]:
    """201 with ``Location`` when it wrote; 200 with the plan when it was a dry run.

    A dry run created nothing, so naming a resource that does not exist would be a lie the client
    has no way to detect.
    """
    if result.wrote:
        response.headers["Location"] = location
    else:
        response.status_code = status.HTTP_200_OK
    return s.write_result_to_dict(result)


def _deleted(result: Any, response: Response, *, dry_run: bool) -> dict[str, Any] | None:
    """204 with no body when it deleted; 200 with the plan when it was a dry run."""
    if dry_run:
        response.status_code = status.HTTP_200_OK
        return s.write_result_to_dict(result)
    return None


def _require_admin() -> None:
    if not s.is_admin_mode():
        raise HTTPException(403, "Admin mode is not enabled — restart the server with --admin-mode")


# ── Server info ───────────────────────────────────────────────────────────────


@router.get("/server-info")
def server_info() -> dict[str, Any]:
    """Return server configuration including admin-mode and read-only status."""
    return {
        "admin_mode": s.is_admin_mode(),
        "read_only": s.is_read_only(),
        "engagement_root": str(r) if (r := s.maybe_engagement_root()) else None,
        "enterprise_root": str(r) if (r := s.maybe_enterprise_root()) else None,
    }


# ── Entity endpoints (enterprise) ────────────────────────────────────────────


class AdminCreateEntityBody(BaseModel):
    artifact_type: str
    name: str
    summary: str | None = None
    properties: dict[str, str] | None = None
    notes: str | None = None
    keywords: list[str] | None = None
    version: str = "0.1.0"
    status: str = "draft"
    dry_run: bool = True


class AdminEditEntityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    summary: str | None = None
    properties: dict[str, str] | None = None
    notes: str | None = None
    keywords: list[str] | None = None
    version: str | None = None
    status: str | None = None
    dry_run: bool = True





@router.post("/entities", status_code=status.HTTP_201_CREATED,
    response_model=WriteResultResponse, responses=_ADMIN_CREATE_RESPONSES)
def admin_create_entity(body: AdminCreateEntityBody, response: Response) -> dict[str, Any]:
    _require_admin()
    ent_root, _, verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_create_entity as _create

    try:
        result = s.authorized_write(
            "admin_create_entity", 
            _create,
            repo_root=ent_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_type=body.artifact_type,
            name=body.name,
            summary=body.summary,
            properties=body.properties,
            notes=body.notes,
            keywords=body.keywords,
            artifact_id=None,
            version=body.version,
            status=body.status,
            last_updated=None,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _created(result, response, f"/admin/api/entities/{result.artifact_id}")


@router.patch("/entities/{artifact_id}",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def admin_edit_entity(artifact_id: str, body: AdminEditEntityBody) -> dict[str, Any]:
    _require_admin()
    ent_root, registry, verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import _UNSET
    from src.infrastructure.write.artifact_write.admin_ops import admin_edit_entity as _edit

    provided = body.model_fields_set
    try:
        result = s.authorized_write(
            "admin_update_entity", 
            _edit,
            repo_root=ent_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            name=body.name,
            summary=body.summary if "summary" in provided else _UNSET,
            properties=body.properties if "properties" in provided else _UNSET,
            notes=body.notes if "notes" in provided else _UNSET,
            keywords=body.keywords if "keywords" in provided else _UNSET,
            version=body.version,
            status=body.status,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


@router.delete("/entities/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None, responses=_ADMIN_DELETE_RESPONSES)
def admin_delete_entity(
    artifact_id: str, response: Response, dry_run: bool = True
) -> dict[str, Any] | None:
    _require_admin()
    ent_root, registry, _verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_delete_entity as _delete

    try:
        result = s.authorized_write(
            "admin_delete_entity", 
            _delete,
            repo_root=ent_root,
            registry=registry,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            dry_run=dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _deleted(result, response, dry_run=dry_run)


# ── Connection endpoints (enterprise) ────────────────────────────────────────


class AdminAddConnectionBody(BaseModel):
    source_entity: str
    connection_type: str
    target_entity: str
    description: str | None = None
    dry_run: bool = True


@router.post("/connections", status_code=status.HTTP_201_CREATED,
    response_model=WriteResultResponse, responses=_ADMIN_CREATE_RESPONSES)
def admin_add_connection(body: AdminAddConnectionBody, response: Response) -> dict[str, Any]:
    _require_admin()
    ent_root, registry, verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_add_connection as _add

    try:
        result = s.authorized_write(
            "admin_create_connection", 
            _add,
            repo_root=ent_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            source_entity=body.source_entity,
            connection_type=body.connection_type,
            target_entity=body.target_entity,
            description=body.description,
            version="0.1.0",
            status="active",
            last_updated=None,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _created(result, response, f"/admin/api/connections/{result.artifact_id}")


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None, responses=_ADMIN_DELETE_RESPONSES)
def admin_remove_connection(
    connection_id: str, response: Response, dry_run: bool = True
) -> dict[str, Any] | None:
    _require_admin()
    # A connection's identity is the single-segment composite ``{src}---{tgt}@@{type}`` — the same
    # string the read surface emits — so the endpoints come out of the path, not a body.
    from src.domain.artifact_id import MalformedArtifactIdError, parse_connection_id  # noqa: PLC0415

    try:
        key = parse_connection_id(connection_id)
    except MalformedArtifactIdError:
        raise HTTPException(404, f"Not found: {connection_id!r}") from None
    ent_root, registry, verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_remove_connection as _remove

    try:
        result = s.authorized_write(
            "admin_delete_connection", 
            _remove,
            repo_root=ent_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            source_entity=key.src_short,
            connection_type=key.type,
            target_entity=key.tgt_short,
            dry_run=dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _deleted(result, response, dry_run=dry_run)


# ── Diagram endpoints (enterprise) ───────────────────────────────────────────


class AdminCreateDiagramBody(BaseModel):
    diagram_type: str
    name: str
    entity_ids: list[str]
    connection_ids: list[str]
    keywords: list[str] | None = None
    version: str = "0.1.0"
    status: str = "active"
    dry_run: bool = True





@router.post("/diagrams", status_code=status.HTTP_201_CREATED,
    response_model=WriteResultResponse, responses=_ADMIN_CREATE_RESPONSES)
def admin_create_diagram(body: AdminCreateDiagramBody, response: Response) -> dict[str, Any]:
    """Create a diagram in the enterprise (global) repository.

    Uses the same diagram creation logic as the engagement router but the
    enterprise root is passed as repo_root.  The boundary check in create_diagram
    would reject this — so this endpoint calls the shared formatting and file-writing
    logic directly via the verifier, bypassing the engagement guard entirely.
    """
    _require_admin()
    ent_root, _, verifier = s.get_admin_write_deps()
    from src.application.identifier_allocator import get_default_allocator
    from src.application.modeling.artifact_write import prefix_for_diagram_type
    from src.infrastructure.gui.routers._diagram_selection import resolve_diagram_selection
    from src.infrastructure.rendering.diagram_builder import generate_archimate_puml_body

    # Import the core diagram writing helper that wraps format + write + render
    from src.infrastructure.write.artifact_write.admin_ops import _write_diagram_to_enterprise
    from src.infrastructure.write.artifact_write.boundary import assert_enterprise_write_root

    assert_enterprise_write_root(ent_root)
    repo = s.get_repo()
    entities, connections, _, _ = resolve_diagram_selection(repo, body.entity_ids, body.connection_ids)
    puml = generate_archimate_puml_body(body.name, entities, connections, diagram_type=body.diagram_type)
    try:
        result = s.authorized_write(
            "admin_create_diagram", 
            _write_diagram_to_enterprise,
            repo_root=ent_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            diagram_type=body.diagram_type,
            name=body.name,
            puml=puml,
            artifact_id=get_default_allocator().allocate(
                prefix=prefix_for_diagram_type(body.diagram_type), name_hint=body.name
            ),
            keywords=body.keywords,
            version=body.version,
            status=body.status,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _created(result, response, f"/admin/api/diagrams/{result.artifact_id}")


@router.delete("/diagrams/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None, responses=_ADMIN_DELETE_RESPONSES)
def admin_delete_diagram(
    artifact_id: str, response: Response, dry_run: bool = True
) -> dict[str, Any] | None:
    _require_admin()
    ent_root, _registry, _verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_delete_diagram as _delete

    try:
        result = s.authorized_write(
            "admin_delete_diagram", 
            _delete,
            repo_root=ent_root,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            dry_run=dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _deleted(result, response, dry_run=dry_run)
