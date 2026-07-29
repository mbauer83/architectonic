"""Admin-mode endpoints — write access to both enterprise and engagement repos.

Active only when the GUI server is started with ``--admin-mode``.  All write
operations target the enterprise repo and go through ``admin_ops.py``, which
enforces ``assert_enterprise_write_root`` at every entry point.  The MCP tool
surface is entirely separate and calls the standard write functions (which
unconditionally enforce ``assert_engagement_write_root``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.infrastructure.gui.routers import state as s

router = APIRouter(prefix="/admin/api", tags=["admin"])


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
    artifact_id: str
    name: str | None = None
    summary: str | None = None
    properties: dict[str, str] | None = None
    notes: str | None = None
    keywords: list[str] | None = None
    version: str | None = None
    status: str | None = None
    dry_run: bool = True


class AdminDeleteEntityBody(BaseModel):
    artifact_id: str
    dry_run: bool = True


@router.post("/entity")
def admin_create_entity(body: AdminCreateEntityBody) -> dict[str, Any]:
    _require_admin()
    ent_root, _, verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_create_entity as _create

    try:
        result = s.authorized_write(("POST", "/admin/api/entity"), 
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
    return s.write_result_to_dict(result)


@router.post("/entity/edit")
def admin_edit_entity(body: AdminEditEntityBody) -> dict[str, Any]:
    _require_admin()
    ent_root, registry, verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import _UNSET
    from src.infrastructure.write.artifact_write.admin_ops import admin_edit_entity as _edit

    provided = body.model_fields_set
    try:
        result = s.authorized_write(("POST", "/admin/api/entity/edit"), 
            _edit,
            repo_root=ent_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
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


@router.post("/entity/remove")
def admin_delete_entity(body: AdminDeleteEntityBody) -> dict[str, Any]:
    _require_admin()
    ent_root, registry, _verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_delete_entity as _delete

    try:
        result = s.authorized_write(("POST", "/admin/api/entity/remove"), 
            _delete,
            repo_root=ent_root,
            registry=registry,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


# ── Connection endpoints (enterprise) ────────────────────────────────────────


class AdminAddConnectionBody(BaseModel):
    source_entity: str
    connection_type: str
    target_entity: str
    description: str | None = None
    dry_run: bool = True


class AdminRemoveConnectionBody(BaseModel):
    source_entity: str
    connection_type: str
    target_entity: str
    dry_run: bool = True


@router.post("/connection")
def admin_add_connection(body: AdminAddConnectionBody) -> dict[str, Any]:
    _require_admin()
    ent_root, registry, verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_add_connection as _add

    try:
        result = s.authorized_write(("POST", "/admin/api/connection"), 
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
    return s.write_result_to_dict(result)


@router.post("/connection/remove")
def admin_remove_connection(body: AdminRemoveConnectionBody) -> dict[str, Any]:
    _require_admin()
    ent_root, registry, verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_remove_connection as _remove

    try:
        result = s.authorized_write(("POST", "/admin/api/connection/remove"), 
            _remove,
            repo_root=ent_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            source_entity=body.source_entity,
            connection_type=body.connection_type,
            target_entity=body.target_entity,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


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


class AdminDeleteDiagramBody(BaseModel):
    artifact_id: str
    dry_run: bool = True


@router.post("/diagram")
def admin_create_diagram(body: AdminCreateDiagramBody) -> dict[str, Any]:
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
        result = s.authorized_write(("POST", "/admin/api/diagram"), 
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
    return s.write_result_to_dict(result)


@router.post("/diagram/remove")
def admin_delete_diagram(body: AdminDeleteDiagramBody) -> dict[str, Any]:
    _require_admin()
    ent_root, _registry, _verifier = s.get_admin_write_deps()
    from src.infrastructure.write.artifact_write.admin_ops import admin_delete_diagram as _delete

    try:
        result = s.authorized_write(("POST", "/admin/api/diagram/remove"), 
            _delete,
            repo_root=ent_root,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)
