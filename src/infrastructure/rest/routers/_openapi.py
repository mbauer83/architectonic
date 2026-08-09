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

The ``OpenMapResponse`` placeholder those 69 operations shared is gone, with the last of them: the
response-contract ledger is empty, so there is nothing left for it to stand in for.

The exceptions are rostered by name in ``contracts/open_models.py``, each with its reason, and
``tests/architecture/test_open_response_models.py`` holds that no others exist.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from src.infrastructure.rest.contracts.errors import ErrorEnvelope
from src.infrastructure.rest.contracts.verification import WriteVerificationResponse

#: FastAPI tag names, one per surface, so ``/docs`` groups by concept.
#:
#: **Every served operation must carry exactly one of these**, which
#: ``tests/architecture/test_openapi_tags.py`` holds. Tags were previously optional and 59 of 166
#: operations had none, so ``/docs`` presented a third of the surface — the whole assurance module, plus
#: sync, promotion and the event stream — under an unnamed "default" heading. A tag is the only thing
#: that makes a 166-operation document navigable, and the omission was invisible because nothing
#: compared the served surface against a vocabulary.
#:
#: Declared on the router (``APIRouter(tags=[...])``) rather than per route: a section is a property of
#: the module, every route in it shares one, and stating it once means a new route inherits it instead
#: of needing to remember it.
#:
#: Not derived from the route-policy manifest, though that was the first plan. The manifest's row groups
#: and these sections genuinely disagree in about ten places, and the disagreements are deliberate — the
#: three search operations are grouped together for *addressing* and want tagging by the artifact kind
#: each one searches, which is what a reader looks under. Addressing and documentation are different
#: concerns over the same operations; coupling them would have made one hostage to the other.
TAG_ENTITIES = "entities"
TAG_CONNECTIONS = "connections"
TAG_DIAGRAMS = "diagrams"
TAG_VIEWPOINTS = "viewpoints"
TAG_DOCUMENTS = "documents"
TAG_GROUPS = "groups"
TAG_TAXONOMY = "taxonomy"
TAG_SYNC = "sync"
TAG_PROMOTION = "promotion"
TAG_PLATFORM = "platform"
TAG_SCRATCHPADS = "scratchpads"

#: The assurance surface, subdivided along the sub-routers it already composes.
#:
#: One `assurance` tag would hold 62 operations — twice the next largest section — which is a heading a
#: reader collapses rather than uses. The twelve sub-routers were already the module's own partition;
#: these six sections group them by the question a reader arrives with, so nothing had to be invented.
TAG_ASSURANCE_STORE = "assurance: store"
TAG_ASSURANCE_ANALYSES = "assurance: analyses"
TAG_ASSURANCE_NODES = "assurance: nodes & edges"
TAG_ASSURANCE_FMEA = "assurance: FMEA"
TAG_ASSURANCE_ARGUMENTS = "assurance: arguments"
TAG_ASSURANCE_SECURITY = "assurance: security signals"

#: Every tag the served surface may use. The fitness function compares against this, so a new section
#: is a deliberate addition here rather than a string that quietly becomes its own heading.
ALL_TAGS: frozenset[str] = frozenset({
    TAG_ENTITIES, TAG_CONNECTIONS, TAG_DIAGRAMS, TAG_VIEWPOINTS, TAG_DOCUMENTS, TAG_GROUPS,
    TAG_TAXONOMY, TAG_SYNC, TAG_PROMOTION, TAG_PLATFORM, TAG_SCRATCHPADS, "admin",
    TAG_ASSURANCE_STORE, TAG_ASSURANCE_ANALYSES, TAG_ASSURANCE_NODES, TAG_ASSURANCE_FMEA,
    TAG_ASSURANCE_ARGUMENTS, TAG_ASSURANCE_SECURITY,
})


class WriteResultResponse(BaseModel):
    """The shape every mutation returns (mirrors ``state.write_result_to_dict`` and the
    frontend ``WriteResultSchema``).

    Closed, unlike the documented-but-open models above. It was open, which made the manifest name a
    contract that promised nothing: `additionalProperties: true` says "these fields, and possibly
    anything else", so a client could not rely on the shape and a fitness function could not tell the
    difference between a typed mutation response and an untyped one. Every mutation returns exactly
    ``state.write_result_to_dict``, so there is nothing extra to keep.

    "Closed" was still half true while ``verification`` was a ``dict[str, Any]``: the *envelope*
    forbade extras and the field inside it published ``additionalProperties: true``, on every
    mutation the surface serves. The field type carries the contract now
    (:class:`WriteVerificationResponse`), and ``test_open_response_models.py`` reads the published
    schema rather than ``model_config`` so the next one of these cannot hide the same way.

    Nothing here carries a default, because ``write_result_to_dict`` (``state.py:387``) emits all six
    keys on every mutation. A default would have published ``content?: string | null`` for a key the
    surface always sends, and the frontend decoder — which required it — would then have been *stricter*
    than the document it is checked against.
    """

    model_config = ConfigDict(extra="forbid")

    wrote: bool
    path: str
    artifact_id: str
    content: str | None
    warnings: list[str]
    verification: WriteVerificationResponse | None



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
