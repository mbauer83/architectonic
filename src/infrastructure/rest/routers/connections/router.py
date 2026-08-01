"""Connection read and write endpoints."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, field_validator

from src.application.entity_type_predicates import is_internal_entity_type
from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.artifact_id import ConnectionKey, MalformedArtifactIdError, parse_connection_id
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.rest.contracts.connections import BrokenReferenceCleanupResponse
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import (
    READ_RESPONSES,
    TAG_CONNECTIONS,
    WRITE_RESPONSES,
    WriteResultResponse,
)
from src.infrastructure.rest.routers.connections.read_routes import register_connection_read_routes

# Accepted multiplicity formats: n  |  n..m  |  n..*  |  *
_MULTIPLICITY_RE = re.compile(r"^\d+$|^\d+\.\.\d+$|^\d+\.\.\*$|^\*$")


def _check_multiplicity(v: str | None) -> str | None:
    if v is not None and v != "" and not _MULTIPLICITY_RE.match(v):
        raise ValueError(f"Invalid multiplicity '{v}': accepted forms are n, n..m, n..*, or *")
    return v


router = APIRouter()


register_connection_read_routes(router)


class _Body(BaseModel):
    """`extra="forbid"`, and no identity field: identity is in the path now, and a body that also
    accepted it would give a caller two places to say which connection they meant."""

    model_config = ConfigDict(extra="forbid")


#: A create answers 201 and names the resource in ``Location``; a dry run created nothing, so it
#: answers 200 with its plan. Both are declared, because a status a handler can return that the
#: document does not mention is a contract no client can rely on.
_CREATE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was created"},
}

#: A detail route can also answer 404, because a malformed or absent composite id is an
#: unaddressable resource rather than a bad request.
_DETAIL_RESPONSES: dict[int | str, Any] = {**WRITE_RESPONSES, **READ_RESPONSES}

_DELETE_RESPONSES: dict[int | str, Any] = {
    **_DETAIL_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was removed"},
}


def _endpoints_of(connection_id: str) -> ConnectionKey:
    """The endpoint pair and type a composite connection id names.

    A malformed id is a 404 rather than a 400: an identifier outside the grammar names no resource,
    and answering differently from an absent one would disclose which of two ids is *shaped* like a
    real one.
    """
    try:
        return parse_connection_id(connection_id)
    except MalformedArtifactIdError:
        raise HTTPException(404, f"Not found: {connection_id!r}") from None


class AddConnectionBody(_Body):
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


def _reject_if_non_entity_gar(artifact_id: str, role: str, catalogs: RuntimeCatalogs) -> None:
    """Raise 400 if the given artifact is a document/diagram GAR (not valid as connection endpoint)."""
    repo = s.maybe_get_repo()
    rec = repo.get_entity(artifact_id) if repo is not None else None
    if rec is None:
        return
    is_non_entity_gar = (
        is_internal_entity_type(rec.artifact_type, catalogs.ontology)
        and rec.extra.get("global-artifact-type") != "entity"
    )
    if is_non_entity_gar:
        raise HTTPException(400, f"Cannot use a document/diagram global-artifact-reference as a connection {role}")


@router.post("/api/connections", tags=[TAG_CONNECTIONS], summary="Add a connection between two entities",
    response_model=WriteResultResponse, responses=_CREATE_RESPONSES,
    status_code=status.HTTP_201_CREATED)
def add_connection(
    body: AddConnectionBody,
    response: Response,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
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
        gar_result = s.authorized_write(
            "connections_create_connection", 
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
    _reject_if_non_entity_gar(body.source_entity, "source", catalogs)
    _reject_if_non_entity_gar(body.target_entity, "target", catalogs)

    _enterprise_root = s.maybe_enterprise_root()
    if _enterprise_root is not None and registry.scope_of_entity(body.source_entity) == "enterprise":
        gar_source_id = _ensure_gar(body.source_entity)
        effective_source = gar_source_id

    if _enterprise_root is not None and registry.scope_of_entity(body.target_entity) == "enterprise":
        gar_artifact_id = _ensure_gar(body.target_entity)
        effective_target = gar_artifact_id

    try:
        result = s.authorized_write(
            "connections_create_connection", 
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
    # A dry run created nothing, so it reports a plan with 200 — never a 201 naming a resource that
    # does not exist. A real create names it, in Location as well as in the body.
    if result.wrote:
        response.headers["Location"] = f"/api/connections/{result.artifact_id}"
    else:
        response.status_code = status.HTTP_200_OK
    return d


class EditConnectionBody(_Body):
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


class ConnectionAssociateBody(_Body):
    add_entities: list[str] | None = None
    remove_entities: list[str] | None = None
    dry_run: bool = True


@router.patch("/api/connections/{connection_id}", tags=[TAG_CONNECTIONS],
    summary="Edit a connection's attributes", response_model=WriteResultResponse,
    responses=_DETAIL_RESPONSES)
def edit_connection(connection_id: str, body: EditConnectionBody) -> dict[str, Any]:
    key = _endpoints_of(connection_id)
    repo_root, registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.connection_edit import _UNSET
    from src.infrastructure.write.artifact_write.connection_edit import edit_connection as _edit

    provided = body.model_fields_set
    try:
        result = s.authorized_write(
            "connections_update_connection", 
            _edit,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            source_entity=key.src_short,
            connection_type=key.type,
            target_entity=key.tgt_short,
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


@router.patch("/api/connections/{connection_id}/associated-entities", tags=[TAG_CONNECTIONS],
    summary="Add/remove a connection's associated entities", response_model=WriteResultResponse,
    responses=_DETAIL_RESPONSES)
def manage_connection_associations(
    connection_id: str, body: ConnectionAssociateBody
) -> dict[str, Any]:
    """A delta over a set-valued relation, which is why it is a PATCH rather than a PUT: the caller
    says what to add and remove, not what the whole set should become."""
    key = _endpoints_of(connection_id)
    repo_root, registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.connection_edit import edit_connection_associations as _assoc

    try:
        result = s.authorized_write(
            "connections_update_connection_associations", 
            _assoc,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            source_entity=key.src_short,
            connection_type=key.type,
            target_entity=key.tgt_short,
            add_entities=body.add_entities,
            remove_entities=body.remove_entities,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


@router.delete("/api/connections/{connection_id}", tags=[TAG_CONNECTIONS],
    summary="Remove a connection", response_model=None, responses=_DELETE_RESPONSES,
    status_code=status.HTTP_204_NO_CONTENT)
def remove_connection(
    connection_id: str, response: Response, dry_run: bool = True
) -> dict[str, Any] | None:
    key = _endpoints_of(connection_id)
    repo_root, registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.connection_edit import remove_connection as _remove

    try:
        result = s.authorized_write(
            "connections_delete_connection", 
            _remove,
            repo_root=repo_root,
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
    # A committed removal has nothing to report; a dry run has its plan, which needs a status that
    # permits a body.
    if dry_run:
        response.status_code = status.HTTP_200_OK
        return s.write_result_to_dict(result)
    return None


# ── Broken-reference cleanup ──────────────────────────────────────────────────


class CleanupBrokenRefsBody(_Body):
    dry_run: bool = True


@router.post("/api/connections/cleanup-broken-refs", tags=[TAG_CONNECTIONS],
    summary="Remove connections whose target no longer exists",
    response_model=BrokenReferenceCleanupResponse, responses=WRITE_RESPONSES)
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
