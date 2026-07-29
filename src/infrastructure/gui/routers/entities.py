"""Entity read and write endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from src.application._artifact_query_helpers import read_entity as serialize_entity
from src.application._diagram_entity_extraction import extract_diagram_entities
from src.application.artifact_parsing import decode_entity_properties, parse_entity_content_sections
from src.application.artifact_schema import load_attribute_schema
from src.application.document_links import reference_dicts_for_entity
from src.application.entity_type_predicates import is_internal_entity_type
from src.application.read_models import EntityContextReadModel
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._openapi import (
    READ_RESPONSES,
    TAG_ENTITIES,
    TAG_TAXONOMY,
    WRITE_RESPONSES,
    DocumentedModel,
    OpenMapResponse,
    WriteResultResponse,
)
from src.infrastructure.gui.routers.entity_listing import (
    _catalogs,
    build_entity_list_rows,
    select_entity_population,
)

router = APIRouter()


# ── Response models (key fields documented; extras kept via DocumentedModel) ────


class EntitySummaryResponse(DocumentedModel):
    artifact_id: str
    artifact_type: str
    name: str
    version: str
    status: str
    domain: str
    subdomain: str
    path: str
    is_global: bool
    last_updated: str | None = None


class EntityListResponse(DocumentedModel):
    total: int
    items: list[EntitySummaryResponse]


class EntityDetailResponse(DocumentedModel):
    artifact_id: str
    artifact_type: str
    name: str
    version: str
    status: str
    domain: str
    subdomain: str
    path: str
    last_updated: str | None = None


class EntitySchemaResponse(DocumentedModel):
    artifact_type: str
    specialization: str
    # ``schema`` (the JSON Schema itself) flows through via extra="allow"; declaring it would
    # shadow BaseModel.schema. The documented fields are the ones a client branches on.
    properties: list[str]
    required: list[str]
    descriptors: dict[str, Any]
    conflicts: list[str]
    quarantined: bool


@router.get("/api/stats", tags=[TAG_TAXONOMY], summary="Repository-wide artifact counts",
    response_model=OpenMapResponse)
def get_stats() -> dict[str, Any]:
    return s.get_repo().stats()


@router.get("/api/backend-identity", tags=[TAG_TAXONOMY], summary="Backend identity and workspace roots",
    response_model=OpenMapResponse)
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
    response_model=EntityListResponse)
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


@router.get("/api/entity", tags=[TAG_ENTITIES], summary="Read one entity by id", response_model=EntityDetailResponse,
    responses=READ_RESPONSES)
def read_entity(id: str) -> dict[str, Any]:
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


@router.get("/api/entity-context", tags=[TAG_ENTITIES], summary="Read an entity with its connection context",
    responses=READ_RESPONSES)
def read_entity_context(id: str) -> EntityContextReadModel:
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


@router.get("/api/entity-schemata", tags=[TAG_ENTITIES],
    summary="Effective attribute schema for a (type, specialization) pair", response_model=EntitySchemaResponse)
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


class CreateEntityBody(BaseModel):
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


class EditEntityBody(BaseModel):
    artifact_id: str
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


class DeleteEntityBody(BaseModel):
    artifact_id: str
    dry_run: bool = True


@router.post("/api/entity", tags=[TAG_ENTITIES], summary="Create an entity (dry-run or committed)",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def create_entity(body: CreateEntityBody) -> dict[str, Any]:
    if is_internal_entity_type(body.artifact_type, _catalogs().ontology):
        raise HTTPException(400, "global-artifact-reference entities cannot be created directly")
    repo_root, _registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.entity import create_entity as _create

    try:
        result = s.authorized_write(("POST", "/api/entity"), 
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
    return s.write_result_to_dict(result)


@router.post("/api/entity/edit", tags=[TAG_ENTITIES], summary="Edit an entity (partial update)",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def edit_entity(body: EditEntityBody) -> dict[str, Any]:
    repo_root, registry, verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.entity_edit import _UNSET
    from src.infrastructure.write.artifact_write.entity_edit import edit_entity as _edit

    provided = body.model_fields_set
    try:
        result = s.authorized_write(("POST", "/api/entity/edit"), 
            _edit,
            repo_root=repo_root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
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


@router.post("/api/entity/remove", tags=[TAG_ENTITIES], summary="Delete an entity",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def delete_entity(body: DeleteEntityBody) -> dict[str, Any]:
    repo_root, registry, _verifier = s.get_write_deps()
    from src.infrastructure.write.artifact_write.entity_delete import delete_entity as _delete

    try:
        result = s.authorized_write(("POST", "/api/entity/remove"), 
            _delete,
            repo_root=repo_root,
            registry=registry,
            clear_repo_caches=s.clear_caches,
            artifact_id=body.artifact_id,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return s.write_result_to_dict(result)
