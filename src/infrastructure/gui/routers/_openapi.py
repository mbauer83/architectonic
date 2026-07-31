"""Shared OpenAPI documentation infrastructure for the modeling & querying REST surface.

FastAPI already serves ``/openapi.json`` + ``/docs``; the gap is fidelity — untyped 200
bodies, no tags, no declared error statuses. The fix is to let the **types drive the schema**:
handlers annotate a ``response_model`` and FastAPI generates the schema from it, so nothing is
hand-written per operation. The pieces here are the ones that genuinely cannot come from a
return type — the tag names and the small shared error contract — plus two response-model base
classes the routers subclass.

**Response models are closed.** This docstring used to say the opposite — declare the key fields, set
``extra="allow"``, let the rest through undocumented — and that advice is what produced 69 operations
publishing ``additionalProperties: true``. It reads as prudent (no field is ever dropped) and costs a
client the only thing a schema is for: knowing which fields arrive. Models now use ``extra="forbid"``
and are derived from the producer, so a payload the contract does not describe fails here rather than
reaching a consumer that was promised otherwise.

The exceptions are rostered by name in ``contracts/open_models.py``, each with its reason, and
``tests/architecture/test_open_response_models.py`` holds that no others exist.
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


class OpenMapResponse(BaseModel):
    """The migration placeholder: an operation whose response has not been derived from its producer yet.

    Not a decision, and not "a genuinely dynamic map" as this docstring once claimed — that reading is
    what let it spread to a third of the surface. Every operation still using it is listed in
    ``route_policy._response_contracts.UNTYPED_RESPONSE_OPERATIONS``, a shrink-only ledger, and a
    fitness function refuses this model on any operation absent from it. **Do not annotate a new handler
    with this.** Derive a closed DTO from what the handler returns; that is cheap when the code is in
    front of you and expensive once a client depends on the ambiguity.
    """

    model_config = ConfigDict(extra="allow")


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



def media_response(media_type: str, description: str) -> dict[int | str, Any]:
    """Declare a success body that is not JSON — a rendered image, a CSV, an event stream.

    FastAPI documents ``application/json`` unless told otherwise, so an operation returning bytes
    published a JSON contract it never honoured: a generated client would decode the body as JSON and
    fail on the first byte. Naming the real media type is what makes the manifest's ``media`` and
    ``stream`` rows true rather than aspirational.

    The content schema is deliberately empty: the bytes have a type, not a shape.

    **Pass ``response_class`` on the route as well.** Without it FastAPI documents its own
    ``application/json`` default *alongside* whatever this declares, and the operation then
    advertises two content types of which one is a fiction. Any Response class whose
    ``media_type`` is ``None`` (``Response``, ``FileResponse``, ``StreamingResponse``) suppresses
    the default and leaves this declaration as the only one.
    """
    return {200: {"content": {media_type: {}}, "description": description}}

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
