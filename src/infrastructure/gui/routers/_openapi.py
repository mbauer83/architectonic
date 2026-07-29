"""Shared OpenAPI documentation infrastructure for the modeling & querying REST surface.

FastAPI already serves ``/openapi.json`` + ``/docs``; the gap is fidelity — untyped 200
bodies, no tags, no declared error statuses. The fix is to let the **types drive the schema**:
handlers annotate a ``response_model`` and FastAPI generates the schema from it, so nothing is
hand-written per operation. The pieces here are the ones that genuinely cannot come from a
return type — the tag names and the small shared error contract — plus two response-model base
classes the routers subclass.

Response models declare their KEY fields and set ``extra="allow"`` (→ ``additionalProperties:
true`` in the schema), so a model documents a shape without having to enumerate every field
and, crucially, without FastAPI dropping fields the handler returns that the model omitted —
the response payload is never altered, only documented.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

#: FastAPI tag names, one per modeling/query surface, so ``/docs`` groups by concept.
TAG_ENTITIES = "entities"
TAG_CONNECTIONS = "connections"
TAG_DIAGRAMS = "diagrams"
TAG_VIEWPOINTS = "viewpoints"
TAG_DOCUMENTS = "documents"
TAG_GROUPS = "groups"
TAG_TAXONOMY = "taxonomy"


class DocumentedModel(BaseModel):
    """Base for response models: declares the fields worth documenting but keeps any extra
    the handler returns (``extra="allow"`` → ``additionalProperties: true``), so annotating a
    handler with one of these documents its shape without changing its payload."""

    model_config = ConfigDict(extra="allow")


class OpenMapResponse(DocumentedModel):
    """A genuinely open/dynamic map (e.g. aggregate stats, composed authoring guidance) —
    documented as an object, no false precision, still no hand-written schema."""


class WriteResultResponse(DocumentedModel):
    """The shape every mutation returns (mirrors ``state.write_result_to_dict`` and the
    frontend ``WriteResultSchema``)."""

    wrote: bool
    path: str
    artifact_id: str
    content: str | None = None
    warnings: list[str] = []
    verification: dict[str, Any] | None = None


# ── Error-response fragments (the statuses the handlers actually return) ─────────

_DETAIL_SCHEMA = {"type": "object", "properties": {"detail": {"type": "string"}}}


def _err(description: str) -> dict[str, Any]:
    return {"description": description, "content": {"application/json": {"schema": _DETAIL_SCHEMA}}}


#: Attach to id-lookup reads: they 404 when the artifact is absent. (422 for bad query params
#: is added automatically by FastAPI.)
READ_RESPONSES: dict[int | str, dict[str, Any]] = {404: _err("Artifact not found")}

#: Attach to write operations. Mirrors the mutation-gate + authorization statuses
#: (``state._rejection_to_http`` / ``authorized_write``).
WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: _err("Validation error (bad or ambiguous write)"),
    403: _err("Write forbidden (e.g. admin mode not enabled, or mutation denied)"),
    409: _err("Write conflict"),
    423: _err("Write temporarily rejected by the workspace gate (retryable)"),
}
