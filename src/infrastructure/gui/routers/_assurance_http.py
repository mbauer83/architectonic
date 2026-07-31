"""Shared HTTP helpers for the assurance read/analysis routers.

Builds the exposure policy from the current context and renders the standard
locked/not-found/ok responses, all with ``Cache-Control: no-store``. Kept
separate so the route modules stay small and consistent.
"""

from __future__ import annotations

from fastapi import status
from fastapi.responses import JSONResponse

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


def ok(payload: dict[str, object]) -> JSONResponse:
    return JSONResponse(content=payload, headers={"Cache-Control": NO_STORE})
