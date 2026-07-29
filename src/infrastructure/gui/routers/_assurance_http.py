"""Shared HTTP helpers for the assurance read/analysis routers.

Builds the exposure policy from the current context and renders the standard
locked/not-found/ok responses, all with ``Cache-Control: no-store``. Kept
separate so the route modules stay small and consistent.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse

from src.application.assurance_exposure import AssuranceExposurePolicy
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext, get_assurance_context

NO_STORE = "no-store"


def build_policy() -> tuple[AssuranceContext, AssuranceExposurePolicy]:
    ctx = get_assurance_context()
    return ctx, AssuranceExposurePolicy(ctx.max_classification, ctx.is_available())


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
