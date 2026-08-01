"""Entity read and write endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict

from src.application._artifact_query_helpers import read_entity as serialize_entity
from src.application._diagram_entity_extraction import extract_diagram_entities
from src.application.artifact_parsing import decode_entity_properties, parse_entity_content_sections
from src.application.artifact_schema import load_attribute_schema
from src.application.document_links import reference_dicts_for_entity
from src.application.entity_type_predicates import is_internal_entity_type
from src.application.read_models import EntityContextReadModel
from src.infrastructure.gui.contracts.catalog import (
    BackendIdentityResponse,
    RepositoryStatsResponse,
)
from src.infrastructure.gui.contracts.entities import (
    EntityContextResponse,
    EntityDetailResponse,
    EntityListResponse,
    EntitySchemaResponse,
)
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._openapi import (
    READ_RESPONSES,
    TAG_ENTITIES,
    TAG_TAXONOMY,
    WRITE_RESPONSES,
    WriteResultResponse,
)
from src.infrastructure.gui.routers.entity_listing import (
    _catalogs,
    build_entity_list_rows,
    select_entity_population,
)

router = APIRouter()


# ── Request bodies ────────────────────────────────────────────────────────────
#
# `extra="forbid"`, and no identity field. Identity is in the path now, and a body that also
# accepted it would give a caller two places to say which entity they meant — with nothing deciding
# which wins when they disagree. Forbidding extras is what turns "the id moved" from a mismatch
# nobody notices into a rejected request.


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


#: A create answers 201 and names the resource in ``Location``; a dry run created nothing, so it
#: answers 200 with its plan. Both are declared, because a status a handler can return that the
#: document does not mention is a contract no client can rely on.
_CREATE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was created"},
}

#: A committed deletion answers 204 and carries no body — FastAPI refuses a response model on one,
#: correctly. The dry-run outcome answers 200 with its plan.
_DELETE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was deleted"},
}


@router.get("/api/stats", tags=[TAG_TAXONOMY], summary="Repository-wide artifact counts",
    response_model=RepositoryStatsResponse)
def get_stats() -> dict[str, Any]:
    return s.get_repo().stats()


@router.get("/api/backend-identity", tags=[TAG_TAXONOMY], summary="Backend identity and workspace roots",
    response_model=BackendIdentityResponse)
def get_backend_identity() -> dict[str, Any]:
    """Realpath-normalized served repo roots + software version.

    Consumed by `arch-repair upgrade --commit`'s guard, which refuses to run against a repo a
    running backend is currently serving; `/api/stats` carries no repo roots, hence this
    dedicated endpoint.
    """
    from importlib.metadata import PackageNotFoundError  # noqa: PLC0415
    from importlib.metadata import version as _pkg_version  # noqa: PLC0415

    try:
        software_version = _pkg_version("architectonic")
    except PackageNotFoundError:
        software_version = "unknown"
    return {
        "repo_roots": [str(root) for root in s.configured_roots()],
        "software_version": software_version,
    }


@router.get("/api/entities", tags=[TAG_ENTITIES], summary="List entities (AND-filtered by scope/type/domain)",
    # `exclude_none`: the client's schema reads these optionals as *absent or value*
    # (`Schema.optional`), which is the shape the pre-DTO handler produced. A closed DTO fills an
    # unset optional with null, and `host_diagram_id: null` fails that decode — every row silently
    # dropped, so the list rendered empty with no error anywhere. The DTOs declare the same policy
    # (`NullsOmitted`) so the published document says it too; the pair is held together by
    # `tests/architecture/test_wire_null_policy.py`.
    response_model=EntityListResponse, response_model_exclude_none=True)
def list_entities(
    request: Request,
    domain: str | None = None,
    artifact_type: str | None = None,
    status: str | None = None,
    scope: str | None = None,
    group: str | None = None,
    meta_ontology: str | None = None,
    sort: str | None = None,
    order: str = "asc",
    limit: int = Query(default=200, le=2000),
    offset: int = 0,
) -> dict[str, Any]:
    repo = s.get_repo()
    entities = select_entity_population(
        repo,
        domain=domain, artifact_type=artifact_type, status=status, group=group, scope=scope,
        allowed_types=_meta_ontology_types(meta_ontology, request),
        sort=sort, order=order,
    )
    page = entities[offset : offset + limit]
    return {"total": len(entities), "items": build_entity_list_rows(page, repo)}


def _meta_ontology_types(meta_ontology: str | None, request: Request) -> frozenset[str] | None:
    """Entity types the named meta-ontology admits, or None for "no restriction"."""
    if not meta_ontology:
        return None
    from src.infrastructure.app_bootstrap import (  # noqa: PLC0415
        module_registry_from_app,
        resolve_meta_ontology_artifact_types,
    )
    allowed = resolve_meta_ontology_artifact_types(meta_ontology, module_registry_from_app(request.app))
    return frozenset(allowed) if allowed is not None else None


@router.get("/api/entities/{artifact_id}", tags=[TAG_ENTITIES], summary="Read one entity by id",
    # `exclude_none` for the same reason as the list read above: the client reads these optionals as
    # absent-or-value, and a null failed the decode of the *whole* record. It cost the entity detail,
    # the GSN and C4 sidebars and both relationship-authoring flows — `conn_in: null` against
    # `Schema.optional(Schema.Number)`. The DTOs declare the matching policy, so the published
    # document says so too.
    response_model=EntityDetailResponse, response_model_exclude_none=True,
    responses=READ_RESPONSES)
def read_entity(artifact_id: str) -> dict[str, Any]:
    id = artifact_id
    repo = s.get_repo()
    result = repo.read_artifact(id, mode="full")
    entity_rec = repo.get_entity(id)
    if result is None and "#" in id:
        diagram_id = id.split("#", 1)[0]
        diagram = repo.get_diagram(diagram_id)
        if diagram is not None:
            entity_rec = next(
                (entity for entity in extract_diagram_entities(diagram) if entity.artifact_id == id),
                None,
            )
            if entity_rec is not None:
                result = serialize_entity(entity_rec, mode="full")
    if result is None:
        raise HTTPException(404, f"Not found: {id!r}")
    if entity_rec is not None:
        parsed = parse_entity_content_sections(entity_rec.content_text)
        result["summary"] = parsed["summary"]
        result["properties"] = parsed["properties"]
        result["notes"] = parsed["notes"]
        inc, sym, out = repo.connection_counts_for(id)
        result["conn_in"] = inc
        result["conn_sym"] = sym
        result["conn_out"] = out
        result["is_global"] = s.is_global(entity_rec.path)
    return result


@router.get("/api/entities/{artifact_id}/context", tags=[TAG_ENTITIES],
    summary="Read an entity with its connection context", response_model=EntityContextResponse,
    response_model_exclude_none=True, responses=READ_RESPONSES)
def read_entity_context(artifact_id: str) -> EntityContextReadModel:
    id = artifact_id
    repo = s.get_repo()
    context = repo.read_entity_context(id)
    if context is None:
        raise HTTPException(404, f"Not found: {id!r}")
    entity_rec = repo.get_entity(id)
    if entity_rec is not None:
        parsed = parse_entity_content_sections(entity_rec.content_text)
        # Decode raw cell strings to typed Python values using the attribute schema.
        repo_root = s.maybe_engagement_root()
        raw_props: dict[str, str] = parsed["properties"]
        artifact_type = entity_rec.artifact_type
        attr_schema = load_attribute_schema(repo_root, artifact_type) if repo_root else None
        prop_schemata: dict[str, dict] = (attr_schema or {}).get("properties", {}) or {}
        _raw_attr_types = entity_rec.extra.get("attribute-types")
        attr_types: dict[str, str] = (
            {k: str(v) for k, v in _raw_attr_types.items()} if isinstance(_raw_attr_types, dict) else {}
        )
        context["entity"]["summary"] = parsed["summary"]
        context["entity"]["properties"] = decode_entity_properties(raw_props, prop_schemata, attr_types)
        context["entity"]["notes"] = parsed["notes"]
        context["entity"]["is_global"] = s.is_global(entity_rec.path)
        context["entity"]["referenced_in_documents"] = reference_dicts_for_entity(
            documents=repo.list_documents(),
            entity=entity_rec,
        )
    return context


@router.get("/api/entity-schemata/{artifact_type}", tags=[TAG_ENTITIES],
    summary="Effective attribute schema for a (type, specialization) pair",
    response_model=EntitySchemaResponse, response_model_exclude_none=True)
def get_entity_schemata(artifact_type: str, specialization: str = "") -> dict[str, Any]:
    """Effective attribute schema for an entity type, merged with the selected
    specialization(s)' contributed attributes — the same schema the verifier validates
    against, so the authoring form and verification can never drift.

    ``specialization`` accepts one slug or a comma-separated list (§15.2 multiple
    specializations); the merge is over the whole applied set, in order."""
    repo_root = s.maybe_engagement_root()
    if repo_root is None:
        raise HTTPException(500, "Repository not initialized")
    from src.application.artifact_schema import (
        attribute_descriptors,
        compute_effective_attribute_schema,
        schema_all_properties,
        schema_required_properties,
    )

    applied = [slug.strip() for slug in specialization.split(",") if slug.strip()]
    schema, conflicts = compute_effective_attribute_schema(
        repo_root,
        artifact_type,
        applied or [""],
        specialization_catalog=_catalogs().specializations,
        profile_registry=_catalogs().profiles,
    )
    # `quarantined` is a derived read of the SAME conflicts channel (not a parallel one):
    # a non-empty conflict set means this (type, specialization) pair is Class B quarantined,
    # so the write boundary (WU-Q3) will refuse a create/edit for it. The GUI reads this to
    # show a banner and disable submit (WU-S2); the flag only explains a refusal the backend
    # already guarantees (PLAN §3 P8).
    quarantined = bool(conflicts)
    if schema is None:
        return {
            "artifact_type": artifact_type,
            "specialization": specialization,
            "schema": None,
            "properties": [],
            "required": [],
            "descriptors": {},
            "conflicts": conflicts,
            "quarantined": quarantined,
        }
    return {
        "artifact_type": artifact_type,
        "specialization": specialization,
        "schema": schema,
        "properties": schema_all_properties(schema),
        "required": schema_required_properties(schema),
        "descriptors": attribute_descriptors(schema),
        "conflicts": conflicts,
        "quarantined": quarantined,
    }


class CreateEntityBody(_Body):
    artifact_type: str
    name: str
    summary: str | None = None
    properties: dict[str, Any] | None = None
    attribute_types: dict[str, str] | None = None
    notes: str | None = None
    keywords: list[str] | None = None
    specialization: str | None = None
    specializations: list[str] | None = None
    version: str = "0.1.0"
    status: str = "draft"
    dry_run: bool = True


class EditEntityBody(_Body):
    name: str | None = None
    summary: str | None = None
    properties: dict[str, Any] | None = None
    attribute_types: dict[str, str] | None = None
    notes: str | None = None
    keywords: list[str] | None = None
    specialization: str | None = None
    specializations: list[str] | None = None
    version: str | None = None
    status: str | None = None
    dry_run: bool = True


@router.post("/api/entities", tags=[TAG_ENTITIES], summary="Create an entity (dry-run or committed)",
    response_model=WriteResultResponse, responses=_CREATE_RESPONSES,
    status_code=status.HTTP_201_CREATED)
def create_entity(body: CreateEntityBody, response: Response) -> dict[str, Any]:
    if is_internal_entity_type(body.artifact_type, _catalogs().ontology):
        raise HTTPException(400, "global-artifact-reference entities cannot be created directly")
    repo_root, _registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.entity import create_entity as _create

    try:
        result = s.authorized_write(
            "entities_create_entity", 
            _create,
            repo_root=repo_root,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_type=body.artifact_type,
            name=body.name,
            summary=body.summary,
            properties=body.properties,
            attribute_types=body.attribute_types,
            notes=body.notes,
            keywords=body.keywords,
            specialization=body.specialization,
            specializations=body.specializations,
            artifact_id=None,
            version=body.version,
            status=body.status,
            last_updated=None,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    # A dry run created nothing, so it is a 200 describing a plan — never a 201 naming a resource
    # that does not exist. A real create names it, in Location as well as in the body.
    if result.wrote:
        response.headers["Location"] = f"/api/entities/{result.artifact_id}"
    else:
        response.status_code = status.HTTP_200_OK
    return s.write_result_to_dict(result)


@router.patch("/api/entities/{artifact_id}", tags=[TAG_ENTITIES], summary="Edit an entity (partial update)",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def edit_entity(artifact_id: str, body: EditEntityBody) -> dict[str, Any]:
    repo_root, registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.entity_edit import _UNSET
    from src.infrastructure.write.artifact_write.entity_edit import edit_entity as _edit

    provided = body.model_fields_set
    try:
        result = s.authorized_write(
            "entities_update_entity", 
            _edit,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            name=body.name,
            summary=body.summary if "summary" in provided else _UNSET,
            properties=body.properties if "properties" in provided else _UNSET,
            attribute_types=body.attribute_types if "attribute_types" in provided else _UNSET,
            notes=body.notes if "notes" in provided else _UNSET,
            keywords=body.keywords if "keywords" in provided else _UNSET,
            specialization=body.specialization if "specialization" in provided else _UNSET,
            specializations=body.specializations if "specializations" in provided else _UNSET,
            version=body.version,
            status=body.status,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)


@router.delete("/api/entities/{artifact_id}", tags=[TAG_ENTITIES], summary="Delete an entity",
    response_model=None, responses=_DELETE_RESPONSES, status_code=status.HTTP_204_NO_CONTENT)
def delete_entity(
    artifact_id: str, response: Response, dry_run: bool = True
) -> dict[str, Any] | None:
    repo_root, registry, _verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.entity_delete import delete_entity as _delete

    try:
        result = s.authorized_write(
            "entities_delete_entity", 
            _delete,
            repo_root=repo_root,
            registry=registry,
            clear_repo_caches=s.clear_caches,
            artifact_id=artifact_id,
            dry_run=dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    # A deletion has nothing to say, so it says nothing. A dry-run deletion has the plan to report,
    # which is a body — and a body needs a status that permits one.
    if dry_run:
        response.status_code = status.HTTP_200_OK
        return s.write_result_to_dict(result)
    return None
