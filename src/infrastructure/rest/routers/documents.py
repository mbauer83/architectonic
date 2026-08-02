"""Document read and write endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from src.application.artifacts.document_schema import get_document_subdirectory, load_document_schemata
from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.rest.contracts.authoring_catalogs import DocumentTypeListResponse
from src.infrastructure.rest.contracts.documents import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentSchemataResponse,
)
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import (
    READ_RESPONSES,
    TAG_DOCUMENTS,
    WRITE_RESPONSES,
    WriteResultResponse,
)

router = APIRouter()


class CreateDocumentRequest(BaseModel):
    doc_type: str
    title: str
    body: str | None = None
    keywords: list[str] | None = None
    extra_frontmatter: dict[str, object] | None = None
    version: str = "0.1.0"
    status: str = "draft"
    last_updated: str | None = None
    dry_run: bool = False


class EditDocumentRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    keywords: list[str] | None = None
    extra_frontmatter: dict[str, object] | None = None
    status: str | None = None
    version: str | None = None
    last_updated: str | None = None
    dry_run: bool = False


def _get_engagement_root() -> Path:
    root = s.maybe_engagement_root()
    if root is None:
        raise HTTPException(500, "Repository not initialized")
    return root


_FIXED_FIELDS = {"title", "status", "keywords"}


def _extra_frontmatter_fields(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract type-specific frontmatter fields from schema (excluding fixed fields)."""
    fm = schema.get("frontmatter_schema", {})
    props = fm.get("properties", {})
    required = set(fm.get("required", []))
    return [
        {
            "name": k,
            "field_type": v.get("type", "string"),
            "array_items_type": v.get("items", {}).get("type") if v.get("type") == "array" else None,
            "required": k in required,
        }
        for k, v in props.items()
        if k not in _FIXED_FIELDS
    ]


@router.get("/api/document-types", tags=[TAG_DOCUMENTS], summary="List document types",
    # `exclude_none` because `SectionSpec.to_dict` omits what it has no value for, and the DTOs declare
    # the matching policy so the published document says so too. One policy for the whole response:
    # a schema shared by two paths cannot claim absent on one and null on the other.
    response_model=DocumentTypeListResponse, response_model_exclude_none=True)
def list_document_types() -> dict[str, object]:
    """Every document type this repository declares, type-ordered.

    An envelope rather than the bare array this used to answer with: every other collection on the
    surface answers with one, and a top-level array cannot later carry a count or a cursor.
    """
    repo_root = _get_engagement_root()
    schemata = load_document_schemata(repo_root)
    return {"document_types": [
        {
            "doc_type": doc_type,
            "abbreviation": schema.get("abbreviation", doc_type.upper()),
            "name": schema.get("name", doc_type),
            "subdirectory": get_document_subdirectory(schema, doc_type),
            "required_sections": schema.get("required_sections", []),
            "sections": schema.get("sections", []),
            "extra_frontmatter_fields": _extra_frontmatter_fields(schema),
            "required_entity_type_connections": schema.get("required_entity_type_connections", []),
            "suggested_entity_type_connections": schema.get("suggested_entity_type_connections", []),
        }
        for doc_type, schema in sorted(schemata.items())
    ]}


@router.get("/api/document-schemata", tags=[TAG_DOCUMENTS], summary="Document frontmatter schemata",
    response_model=DocumentSchemataResponse, response_model_exclude_none=True)
def get_document_schemata() -> dict[str, Any]:
    repo_root = _get_engagement_root()
    return load_document_schemata(repo_root)


@router.get("/api/documents", tags=[TAG_DOCUMENTS], summary="List documents",
    response_model=DocumentListResponse)
def list_documents(
    doc_type: str | None = None,
    status: str | None = None,
    group: str | None = None,
    scope: str | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
) -> dict[str, Any]:
    repo = s.get_repo()
    docs = repo.list_documents(doc_type=doc_type, status=status, group=group)
    # Tier filtering happens BEFORE totals/pagination so `total` is the facet's count.
    if scope == "global":
        docs = [d for d in docs if s.is_global(d.path)]
    elif scope == "engagement":
        docs = [d for d in docs if not s.is_global(d.path)]
    page = docs[offset : offset + limit]
    return {
        "total": len(docs),
        "items": [
            {
                "artifact_id": d.artifact_id,
                "doc_type": d.doc_type,
                "title": d.title,
                "status": d.status,
                "path": str(d.path),
                "keywords": list(d.keywords),
                "sections": list(d.sections),
                "group": d.group,
                "is_global": s.is_global(d.path),
                "last_updated": d.last_updated,
            }
            for d in page
        ],
    }


@router.get("/api/documents/{artifact_id}", tags=[TAG_DOCUMENTS], summary="Read a document by id",
    response_model=DocumentDetailResponse, responses=READ_RESPONSES)
def read_document(artifact_id: str) -> dict[str, Any]:
    repo = s.get_repo()
    result = repo.read_artifact(artifact_id, mode="full")
    doc = repo.get_document(artifact_id)
    if result is None or doc is None:
        raise HTTPException(404, f"Not found: {artifact_id!r}")
    result["is_global"] = s.is_global(doc.path)
    return result


#: A create answers 201 and names the resource in ``Location``. A *dry run* created nothing, so it
#: answers 200 with its plan — declared here, because a status the handler can return that the
#: document does not mention is a contract the client cannot rely on.
_CREATE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was created"},
}


@router.post("/api/documents", tags=[TAG_DOCUMENTS], summary="Create a document",
    response_model=WriteResultResponse, responses=_CREATE_RESPONSES,
    status_code=status.HTTP_201_CREATED)
def create_document(req: CreateDocumentRequest, response: Response,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.document import create_document as _create

    repo_root, _, verifier = s.get_write_deps(catalogs)

    result = s.authorized_write(
            "documents_create_document", 
        _create,
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=s.clear_caches,
        doc_type=req.doc_type,
        title=req.title,
        body=req.body,
        keywords=req.keywords,
        extra_frontmatter=req.extra_frontmatter,
        artifact_id=None,
        version=req.version,
        status=req.status,
        last_updated=req.last_updated,
        dry_run=req.dry_run,
    )
    # A dry run created nothing, so it is a 200 describing a plan — never a 201 naming a resource
    # that does not exist. A real create names it, in Location as well as in the body.
    if result.wrote:
        response.headers["Location"] = f"/api/documents/{result.artifact_id}"
    else:
        response.status_code = status.HTTP_200_OK
    return s.write_result_to_dict(result)


@router.patch("/api/documents/{artifact_id}", tags=[TAG_DOCUMENTS], summary="Edit a document",
    response_model=WriteResultResponse, responses=WRITE_RESPONSES)
def edit_document(artifact_id: str, req: EditDocumentRequest,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.document import edit_document as _edit

    repo_root, _, verifier = s.get_write_deps(catalogs)

    result = s.authorized_write(
            "documents_update_document", 
        _edit,
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=s.clear_caches,
        artifact_id=artifact_id,
        title=req.title,
        body=req.body,
        keywords=req.keywords,
        extra_frontmatter=req.extra_frontmatter,
        status=req.status,
        version=req.version,
        last_updated=req.last_updated,
        dry_run=req.dry_run,
    )
    return s.write_result_to_dict(result)


#: A committed deletion has nothing to report, so 204 is the declared status and there is no
#: response model — FastAPI refuses one, correctly, because a 204 may not carry a body. A *dry
#: run* has its plan to report, so it answers 200, declared as an alternative outcome rather than
#: smuggled into the 204.
_DELETE_RESPONSES: dict[int | str, Any] = {
    **WRITE_RESPONSES,
    200: {"model": WriteResultResponse, "description": "Dry-run plan; nothing was deleted"},
}


@router.delete("/api/documents/{artifact_id}", tags=[TAG_DOCUMENTS], summary="Delete a document",
    response_model=None, responses=_DELETE_RESPONSES, status_code=status.HTTP_204_NO_CONTENT)
def delete_document(artifact_id: str, response: Response, dry_run: bool = False,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any] | None:
    from src.infrastructure.write.artifact_write.document import delete_document as _delete

    repo_root, _, _ = s.get_write_deps(catalogs)

    result = s.authorized_write(
            "documents_delete_document", 
        _delete,
        repo_root=repo_root,
        clear_repo_caches=s.clear_caches,
        artifact_id=artifact_id,
        dry_run=dry_run,
    )
    # A deletion has nothing to say, so it says nothing. A *dry-run* deletion has the plan to
    # report, which is a body — and a body needs a status that permits one.
    if dry_run:
        response.status_code = status.HTTP_200_OK
        return s.write_result_to_dict(result)
    return None
