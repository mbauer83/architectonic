"""Document read and write endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.application.artifact_document_schema import get_document_subdirectory, load_document_schemata
from src.infrastructure.gui.routers import state as s
from src.infrastructure.gui.routers._openapi import READ_RESPONSES, TAG_DOCUMENTS, WRITE_RESPONSES, OpenMapResponse

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
    response_model=list[OpenMapResponse])
def list_document_types() -> list[dict[str, object]]:
    repo_root = _get_engagement_root()
    schemata = load_document_schemata(repo_root)
    return [
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
    ]


@router.get("/api/document-schemata", tags=[TAG_DOCUMENTS], summary="Document frontmatter schemata",
    response_model=OpenMapResponse)
def get_document_schemata() -> dict[str, Any]:
    repo_root = _get_engagement_root()
    return load_document_schemata(repo_root)


@router.get("/api/documents", tags=[TAG_DOCUMENTS], summary="List documents", response_model=OpenMapResponse)
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


@router.get("/api/document", tags=[TAG_DOCUMENTS], summary="Read a document by id", response_model=OpenMapResponse,
    responses=READ_RESPONSES)
def read_document(id: str) -> dict[str, Any]:
    repo = s.get_repo()
    result = repo.read_artifact(id, mode="full")
    if result is None:
        raise HTTPException(404, f"Not found: {id!r}")
    doc = repo.get_document(id)
    if doc is not None:
        result["is_global"] = s.is_global(doc.path)
    return result


@router.post("/api/document", tags=[TAG_DOCUMENTS], summary="Create a document", response_model=OpenMapResponse,
    responses=WRITE_RESPONSES)
def create_document(req: CreateDocumentRequest) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.document import create_document as _create

    repo_root, _, verifier = s.get_write_deps()

    result = s.authorized_write(("POST", "/api/document"), 
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
    return {
        "wrote": result.wrote,
        "artifact_id": result.artifact_id,
        "path": str(result.path),
        "content": result.content,
        "warnings": result.warnings,
        "verification": result.verification,
    }


@router.put("/api/document/{artifact_id}", tags=[TAG_DOCUMENTS], summary="Edit a document",
    response_model=OpenMapResponse, responses=WRITE_RESPONSES)
def edit_document(artifact_id: str, req: EditDocumentRequest) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.document import edit_document as _edit

    repo_root, _, verifier = s.get_write_deps()

    result = s.authorized_write(("PUT", "/api/document/{artifact_id}"), 
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
    return {
        "wrote": result.wrote,
        "artifact_id": result.artifact_id,
        "path": str(result.path),
        "content": result.content,
        "warnings": result.warnings,
        "verification": result.verification,
    }


@router.delete("/api/document/{artifact_id}", tags=[TAG_DOCUMENTS], summary="Delete a document",
    response_model=OpenMapResponse, responses=WRITE_RESPONSES)
def delete_document(artifact_id: str, dry_run: bool = False) -> dict[str, Any]:
    from src.infrastructure.write.artifact_write.document import delete_document as _delete

    repo_root, _, _ = s.get_write_deps()

    result = s.authorized_write(("DELETE", "/api/document/{artifact_id}"), 
        _delete,
        repo_root=repo_root,
        clear_repo_caches=s.clear_caches,
        artifact_id=artifact_id,
        dry_run=dry_run,
    )
    return {
        "wrote": result.wrote,
        "artifact_id": result.artifact_id,
        "path": str(result.path),
        "content": result.content,
        "warnings": result.warnings,
        "verification": result.verification,
    }
