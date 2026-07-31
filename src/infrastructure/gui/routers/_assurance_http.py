"""Shared HTTP helpers for the assurance read/analysis routers.

Builds the exposure policy from the current context and renders the standard
locked/not-found/ok responses, all with ``Cache-Control: no-store``. Kept
separate so the route modules stay small and consistent.
"""

from __future__ import annotations

from fastapi import Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.infrastructure.gui.contracts.errors import ApiError
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext, get_assurance_context

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


def locked_response() -> JSONResponse:
    return JSONResponse(
        status_code=423,
        content={"error": "assurance_store_locked", "message": (
            "The confidential assurance store is not unlocked. "
            "Run `arch-assurance unlock` to enable assurance tools."
        )},
        headers={"Cache-Control": NO_STORE},
    )


def not_found_response() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "not_found"},
        headers={"Cache-Control": NO_STORE},
    )


def ok(payload: dict[str, object], model: type[BaseModel] | None = None) -> JSONResponse:
    """A read's body, with the ``no-store`` every response on this surface carries.

    ``model`` validates the payload against the DTO the route documents. The raw ``JSONResponse`` is
    what the header requires, and FastAPI does not apply ``response_model`` to a response the handler
    built — so the validation the framework would have done happens here, and a declared contract stays
    a checked one rather than documentation of what someone believed. Same seam as the write side's
    ``_ok``; both exist because both must set the header themselves.
    """
    if model is not None:
        model.model_validate(payload)
    return JSONResponse(content=payload, headers={"Cache-Control": NO_STORE})


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
