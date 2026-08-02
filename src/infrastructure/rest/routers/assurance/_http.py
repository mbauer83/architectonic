"""Shared HTTP helpers for the assurance read/analysis routers.

Builds the exposure policy from the current context and renders the standard
locked/not-found/ok responses, all with ``Cache-Control: no-store``. Kept
separate so the route modules stay small and consistent.
"""

from __future__ import annotations

from fastapi import Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.application.assurance.exposure import AssuranceExposurePolicy
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext, get_assurance_context
from src.infrastructure.rest.contracts.errors import ApiError

NO_STORE = "no-store"

_LOCKED_MESSAGE = (
    "The confidential assurance store is not unlocked. "
    "Run `arch-assurance unlock` to enable assurance tools."
)


def build_policy() -> tuple[AssuranceContext, AssuranceExposurePolicy]:
    ctx = get_assurance_context()
    return ctx, AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())


def store_locked() -> ApiError:
    """The locked refusal, as the typed envelope — raised, not returned.

    Returned as an ``ApiError`` for the caller to ``raise``, so the refusal reads at the call site
    as the control-flow break it is, and so every route's declared success type stays the DTO
    rather than widening to include a refusal body.
    """
    return ApiError(status.HTTP_423_LOCKED, "assurance_store_locked", _LOCKED_MESSAGE)


def not_found(message: str) -> ApiError:
    """A not-found refusal in the shared envelope."""
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", message)


def locked_response() -> ApiError:
    """The locked refusal — **raised**, not returned, and in the shared envelope.

    It used to build its own ``{"error": ...}`` body, which is the shape this release tells consumers
    it removed. A client branching on ``detail.code`` fell through on the commonest refusal this
    surface makes, and a locked store is a state the GUI has to render on every page load.
    """
    return store_locked()


def not_found_response() -> ApiError:
    """Not-found, in the envelope, with the identifier withheld.

    The caller supplied the id, so echoing it tells them nothing — and §0e asks this surface to redact
    it, because an absent record and one above the reader's ceiling must be indistinguishable. A body
    that names what was asked for invites the habit of trusting that it existed.
    """
    return not_found("No such assurance record.")


def ok(payload: dict[str, object], model: type[BaseModel] | None = None) -> JSONResponse:
    """A read's body, with the ``no-store`` every response on this surface carries.

    ``model`` validates the payload against the DTO the route documents, **and serialises it**. The
    raw ``JSONResponse`` is what the header requires, and FastAPI does not apply ``response_model`` to
    a response the handler built — so the validation and the serialisation the framework would have
    done both happen here. Same seam as the write side's ``_ok``; both exist because both must set the
    header themselves.

    It used to validate the payload and then serialise the *payload*, discarding the model object it
    had just built. ``model_validate`` applies defaults into that object, so a field the handler
    omitted and the DTO defaults was present in the published document, present in the generated
    client type — ``openapi-typescript`` renders a defaulted response field as required, the server
    being understood always to send it — and absent on the wire. That is the FMEA defect exactly: the
    matrix handler emitted ``dismissal: {}``, ``FmeaCellDismissal`` defaults both of its fields, the
    client's decoder required both, and the whole matrix rendered blank. It was fixed at that one
    producer while nineteen other call sites kept the same seam.
    """
    if model is None:
        return JSONResponse(content=payload, headers={"Cache-Control": NO_STORE})
    return JSONResponse(
        content=model.model_validate(payload).model_dump(mode="json"),
        headers={"Cache-Control": NO_STORE},
    )


def deleted(response: JSONResponse) -> Response:
    """Turn a successful mutation response into ``204`` with no body; pass a refusal through.

    A deletion has nothing to describe, so it reports the absence it created rather than a result
    object — the status convention this release adopts. Written once here rather than by restructuring
    each of the three translators: they refuse over three different result unions, but they all agree
    that success is 200, and that is the only thing this needs to know.

    ``no-store`` rides on the 204 too. It is a header, and the confidentiality contract covers every
    response this surface makes, not only the ones with bodies.
    """
    if response.status_code == 200:
        return Response(status_code=204, headers={"Cache-Control": NO_STORE})
    return response
