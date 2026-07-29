"""Connection read and write endpoints."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from src.application.entity_type_predicates import is_internal_entity_type
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._openapi import TAG_CONNECTIONS, WRITE_RESPONSES, WriteResultResponse
from src.infrastructure.gui.routers.connection_read_routes import _catalogs, register_connection_read_routes

# Accepted multiplicity formats: n  |  n..m  |  n..*  |  *
_MULTIPLICITY_RE = re.compile(r"^\d+$|^\d+\.\.\d+$|^\d+\.\.\*$|^\*$")


def _check_multiplicity(v: str | None) -> str | None:
    if v is not None and v != "" and not _MULTIPLICITY_RE.match(v):
        raise ValueError(f"Invalid multiplicity '{v}': accepted forms are n, n..m, n..*, or *")
    return v


router = APIRouter()


register_connection_read_routes(router)


class AddConnectionBody(BaseModel):
    source_entity: str
    connection_type: str
    target_entity: str
    description: str | None = None
    src_multiplicity: str | None = None
    tgt_multiplicity: str | None = None
    specialization: str | None = None
    specializations: list[str] | None = None
    metadata: dict[str, object] | None = None
    dry_run: bool = True

    @field_validator("src_multiplicity", "tgt_multiplicity")
    @classmethod
    def validate_multiplicity(cls, v: str | None) -> str | None:
        return _check_multiplicity(v)


class RemoveConnectionBody(BaseModel):
    source_entity: str
    connection_type: str
    target_entity: str
    dry_run: bool = True


def _reject_if_non_entity_gar(artifact_id: str, role: str) -> None:
    """Raise 400 if the given artifact is a document/diagram GAR (not valid as connection endpoint)."""
    repo = s.maybe_get_repo()
    rec = repo.get_entity(artifact_id) if repo is not None else None
    if rec is None:
        return
    is_non_entity_gar = (
        is_internal_entity_type(rec.artifact_type, _catalogs().ontology)
        and rec.extra.get("global-artifact-type") != "entity"
    )
    if is_non_entity_gar:
        raise HTTPException(400, f"Cannot use a document/diagram global-artifact-reference as a connection {role}")


@router.post("/api/connection", tags=[TAG_CONNECTIONS], summary="Add a connection between two entities",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def add_connection(body: AddConnectionBody) -> dict[str, Any]:
    repo_root, registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.connection import add_connection as _add

    effective_source = body.source_entity
    effective_target = body.target_entity
    gar_source_id: str | None = None
    gar_artifact_id: str | None = None
    gar_warnings: list[str] = []

    def _ensure_gar(global_id: str) -> str:
        nonlocal registry, verifier
        from src.infrastructure.write.artifact_write.global_artifact_reference import (
            ensure_global_artifact_reference,
        )

        repo = s.get_repo()
        global_rec = repo.get_entity(global_id)
        global_name = global_rec.name if global_rec else global_id
        global_entity_type = global_rec.artifact_type if global_rec else None
        gar_result = s.authorized_write(("POST", "/api/connection"), 
            ensure_global_artifact_reference,
            engagement_repo=repo,
            engagement_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            global_artifact_id=global_id,
            global_artifact_name=global_name,
            global_artifact_type="entity",
            global_artifact_entity_type=global_entity_type,
            dry_run=body.dry_run,
        )
        if gar_result.wrote:
            gar_warnings.append(f"Created global-artifact-reference proxy {gar_result.artifact_id}")
            _, registry, verifier = s.get_write_deps()
        else:
            gar_warnings.append(f"Routed via existing global-artifact-reference {gar_result.artifact_id}")
        return gar_result.artifact_id

    # Reject document/diagram GAR endpoints
    _reject_if_non_entity_gar(body.source_entity, "source")
    _reject_if_non_entity_gar(body.target_entity, "target")

    _enterprise_root = s.maybe_enterprise_root()
    if _enterprise_root is not None and registry.scope_of_entity(body.source_entity) == "enterprise":
        gar_source_id = _ensure_gar(body.source_entity)
        effective_source = gar_source_id

    if _enterprise_root is not None and registry.scope_of_entity(body.target_entity) == "enterprise":
        gar_artifact_id = _ensure_gar(body.target_entity)
        effective_target = gar_artifact_id

    try:
        result = s.authorized_write(("POST", "/api/connection"), 
            _add,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            source_entity=effective_source,
            connection_type=body.connection_type,
            target_entity=effective_target,
            description=body.description,
            src_multiplicity=body.src_multiplicity,
            tgt_multiplicity=body.tgt_multiplicity,
            specialization=body.specialization,
            specializations=body.specializations,
            metadata=body.metadata,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    d = s.write_result_to_dict(result)
    if gar_source_id:
        d["gar_source_id"] = gar_source_id
        d["original_source"] = body.source_entity
    if gar_artifact_id:
        d["gar_artifact_id"] = gar_artifact_id
        d["original_target"] = body.target_entity
    if gar_warnings:
        d["warnings"] = (d.get("warnings") or []) + gar_warnings
    return d


class EditConnectionBody(BaseModel):
    source_entity: str
    connection_type: str
    target_entity: str
    description: str | None = None
    src_multiplicity: str | None = None
    tgt_multiplicity: str | None = None
    specialization: str | None = None
    specializations: list[str] | None = None
    metadata: dict[str, object] | None = None
    dry_run: bool = True

    @field_validator("src_multiplicity", "tgt_multiplicity")
    @classmethod
    def validate_multiplicity(cls, v: str | None) -> str | None:
        return _check_multiplicity(v)


class ConnectionAssociateBody(BaseModel):
    source_entity: str
    connection_type: str
    target_entity: str
    add_entities: list[str] | None = None
    remove_entities: list[str] | None = None
    dry_run: bool = True


@router.post("/api/connection/edit", tags=[TAG_CONNECTIONS], summary="Edit or re-point a connection",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def edit_connection(body: EditConnectionBody) -> dict[str, Any]:
    repo_root, registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.connection_edit import _UNSET
    from src.infrastructure.write.artifact_write.connection_edit import edit_connection as _edit

    provided = body.model_fields_set
    try:
        result = s.authorized_write(("POST", "/api/connection/edit"), 
            _edit,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            source_entity=body.source_entity,
            connection_type=body.connection_type,
            target_entity=body.target_entity,
            description=body.description if "description" in provided else _UNSET,
            src_multiplicity=body.src_multiplicity if "src_multiplicity" in provided else _UNSET,
            tgt_multiplicity=body.tgt_multiplicity if "tgt_multiplicity" in provided else _UNSET,
            specialization=body.specialization if "specialization" in provided else _UNSET,
            specializations=body.specializations if "specializations" in provided else _UNSET,
            metadata=body.metadata if "metadata" in provided else _UNSET,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


@router.post("/api/connection/associate", tags=[TAG_CONNECTIONS],
    summary="Add/remove a connection's associated entities", response_model=WriteResultResponse,
    responses=WRITE_RESPONSES)
def manage_connection_associations(body: ConnectionAssociateBody) -> dict[str, Any]:
    repo_root, registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.connection_edit import edit_connection_associations as _assoc

    try:
        result = s.authorized_write(("POST", "/api/connection/associate"), 
            _assoc,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            source_entity=body.source_entity,
            connection_type=body.connection_type,
            target_entity=body.target_entity,
            add_entities=body.add_entities,
            remove_entities=body.remove_entities,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


@router.post("/api/connection/remove", tags=[TAG_CONNECTIONS], summary="Remove a connection",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def remove_connection(body: RemoveConnectionBody) -> dict[str, Any]:
    repo_root, registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.connection_edit import remove_connection as _remove

    try:
        result = s.authorized_write(("POST", "/api/connection/remove"), 
            _remove,
            repo_root=repo_root,
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


# ── Broken-reference cleanup ──────────────────────────────────────────────────


class CleanupBrokenRefsBody(BaseModel):
    dry_run: bool = True


@router.post("/api/cleanup-broken-refs", tags=[TAG_CONNECTIONS],
    summary="Remove connections whose target no longer exists", response_model=WriteResultResponse,
    responses=WRITE_RESPONSES)
def cleanup_broken_refs(body: CleanupBrokenRefsBody) -> dict[str, Any]:
    """Find and optionally remove broken global-entity-reference proxies.

    A GRF is broken when the enterprise entity it points to no longer exists.
    dry_run=true (default) returns the plan without modifying files.
    """
    import dataclasses

    from src.infrastructure.write.artifact_write.cleanup_broken_refs import cleanup_broken_refs as _cleanup

    eng_root = s.maybe_engagement_root()
    ent_root = s.maybe_enterprise_root()
    if eng_root is None:
        raise HTTPException(500, "Repository not initialized")
    if ent_root is None:
        raise HTTPException(500, "Enterprise repository not configured")
    report = _cleanup(eng_root, ent_root, dry_run=body.dry_run)
    return {
        "dry_run": body.dry_run,
        "broken_grfs": report.broken_grfs,
        "actions": [dataclasses.asdict(a) for a in report.actions],
        "executed": report.executed,
        "errors": report.errors,
    }
