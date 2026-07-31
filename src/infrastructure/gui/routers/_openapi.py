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

from src.infrastructure.gui.contracts.errors import ErrorEnvelope

#: FastAPI tag names, one per modeling/query surface, so ``/docs`` groups by concept.
TAG_ENTITIES = "entities"
TAG_CONNECTIONS = "connections"
TAG_DIAGRAMS = "diagrams"
TAG_VIEWPOINTS = "viewpoints"
TAG_DOCUMENTS = "documents"
TAG_GROUPS = "groups"
TAG_TAXONOMY = "taxonomy"
TAG_ASSURANCE = "assurance"


class DocumentedModel(BaseModel):
    """Base for response models: declares the fields worth documenting but keeps any extra
    the handler returns (``extra="allow"`` → ``additionalProperties: true``), so annotating a
    handler with one of these documents its shape without changing its payload."""

    model_config = ConfigDict(extra="allow")


class OpenMapResponse(DocumentedModel):
    """A genuinely open/dynamic map (e.g. aggregate stats, composed authoring guidance) —
    documented as an object, no false precision, still no hand-written schema."""


class WriteResultResponse(BaseModel):
    """The shape every mutation returns (mirrors ``state.write_result_to_dict`` and the
    frontend ``WriteResultSchema``).

    Closed, unlike the documented-but-open models above. It was open, which made the manifest name a
    contract that promised nothing: `additionalProperties: true` says "these fields, and possibly
    anything else", so a client could not rely on the shape and a fitness function could not tell the
    difference between a typed mutation response and an untyped one. Every mutation returns exactly
    ``state.write_result_to_dict``, so there is nothing extra to keep.
    """

    model_config = ConfigDict(extra="forbid")

    wrote: bool
    path: str
    artifact_id: str
    content: str | None = None
    warnings: list[str] = []
    verification: dict[str, Any] | None = None


# ── Error-response fragments (the statuses the handlers actually return) ─────────
#
# The schema is the typed envelope, not a hand-written ``{"detail": "<string>"}`` fragment. It
# used to be the latter, and that was a promise the surface no longer kept once the central
# handlers started returning a structured ``detail``: a generated client would have decoded every
# error as a string and failed on the object it actually receives.


def _err(description: str) -> dict[str, Any]:
    return {"description": description, "model": ErrorEnvelope}


#: Attach to id-lookup reads: they 404 when the artifact is absent. (422 for a bad query
#: parameter is declared application-wide, since every operation can produce one.)
READ_RESPONSES: dict[int | str, dict[str, Any]] = {404: _err("Artifact not found")}

#: Attach to write operations. Mirrors the mutation-gate + authorization statuses
#: (``state._rejection_to_http`` / ``authorized_write``).
WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: _err("Validation error (bad or ambiguous write)"),
    403: _err("Write forbidden (e.g. admin mode not enabled, or mutation denied)"),
    409: _err("Write conflict"),
    423: _err("Write temporarily rejected by the workspace gate (retryable)"),
}

#: Declared on the application, so every operation's 422 documents the envelope its handler
#: actually returns rather than FastAPI's default ``HTTPValidationError``.
APP_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: _err("Request validation failed"),
    500: _err("Unhandled server error (non-disclosing)"),
}
