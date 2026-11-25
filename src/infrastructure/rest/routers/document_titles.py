"""The name a new document may take: asked of the rule that refuses a taken one, never worked out beside it."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from src.application.artifacts.document_schema import load_document_schemata
from src.infrastructure.rest.contracts.documents import FreeDocumentTitle
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_DOCUMENTS
from src.infrastructure.write.artifact_write._artifact_deduplication import first_free_document_title

router = APIRouter()


@router.get(
    "/api/document-types/{doc_type}/free-title",
    operation_id="documents_read_free_document_title",
    tags=[TAG_DOCUMENTS],
    summary="Read the first name a new document of a type may take",
    response_model=FreeDocumentTitle,
    responses=READ_RESPONSES,
)
def documents_read_free_document_title(
    doc_type: str, title: Annotated[str, Query(min_length=1, description="The name a form would propose.")],
) -> dict[str, str]:
    """*title* where no document of *doc_type* is named so, else *title* numbered "(2)", "(3)", … — the name
    the document create would not refuse as taken. A form proposing a default name asks this, so a second
    analysis of the same architecture is not refused for the first one's name. 404 for an unknown type."""
    root = s.maybe_engagement_root()
    if root is None or doc_type not in load_document_schemata(root):
        raise HTTPException(404, f"No document type {doc_type!r} is declared.")
    return {"doc_type": doc_type, "asked": title, "title": first_free_document_title(s.get_repo(), doc_type, title)}
