"""The three exception handlers and the request-id middleware that make the envelope real.

Three, not one. A single catch-all would leave the 114 existing ``HTTPException`` raise sites
returning ``{"detail": "<a sentence>"}``, so the typed envelope would describe a minority of the
error responses this surface actually produces — a published contract that is false for most of
its own surface is worse than none.

* ``RequestValidationError`` — FastAPI's own 422, with the field errors moved under ``details``.
* ``HTTPException`` — every raise site, mapped to the envelope with its status preserved.
* anything else — a generic 500 whose body never contains the exception's text.

Every error response carries ``Cache-Control: no-store``. That is required on the assurance
surface, where a cached or revalidatable error would let a reader distinguish an above-ceiling
id from an absent one, and it is correct everywhere else too: an error body is a statement about
one moment.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from src.infrastructure.gui.contracts.errors import (
    ApiError,
    DenialDetails,
    ErrorBody,
    ErrorCode,
    ErrorEnvelope,
    FieldError,
    ValidationErrorDetails,
    status_error_code,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

_NO_STORE_HEADERS = {"Cache-Control": "no-store"}

#: Denial codes the write gate treats as retryable, so a client can tell "try again" from "no".
_RETRYABLE_STATUS = 423


def request_id_of(request: Request) -> str:
    """The current request's id, or a fresh one if the middleware did not run.

    Never absent: the id is the only handle a user has on a failure that produced no other
    output, so an error response without one is an error report nobody can follow up.
    """
    existing = getattr(request.state, "request_id", None)
    return str(existing) if existing else uuid.uuid4().hex


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Any]]
) -> Any:
    """Attach an id to the request and echo it on the response.

    Emitted in the envelope *and* as a header so it is quotable whether the caller reads the body
    (a client) or the exchange (a proxy log, a browser network panel).
    """
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def _envelope(
    status_code: int, body: ErrorBody, *, request_id: str, extra: dict[str, str] | None = None
) -> JSONResponse:
    """The envelope, with the headers every error carries — and the refusal's own beneath them.

    ``extra`` goes first so ``no-store`` and the request id cannot be overridden by a caller: the
    confidentiality contract is not a refusal's to relax.
    """
    return JSONResponse(
        status_code=status_code,
        content=ErrorEnvelope(detail=body).model_dump(mode="json"),
        headers={**(extra or {}), **_NO_STORE_HEADERS, REQUEST_ID_HEADER: request_id},
    )


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A raise that had something specific to say. Its details are already validated."""
    assert isinstance(exc, ApiError)
    request_id = request_id_of(request)
    return _envelope(
        exc.status_code,
        ErrorBody(
            code=exc.code, message=exc.message, details=exc.details, request_id=request_id
        ),
        request_id=request_id,
        extra=exc.headers,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """FastAPI's 422. The field errors move under ``details`` rather than replacing the envelope.

    ``loc`` is joined with dots into a path a client can address: ``body.definition.slug`` says
    which input to highlight, where FastAPI's list of mixed strings and indices does not.
    """
    assert isinstance(exc, RequestValidationError)
    request_id = request_id_of(request)
    field_errors = [
        FieldError(
            field=".".join(str(part) for part in error.get("loc", ())),
            message=str(error.get("msg", "invalid")),
        )
        for error in exc.errors()
    ]
    return _envelope(
        422,
        ErrorBody(
            code="validation_error",
            message="The request did not match the expected shape.",
            details=ValidationErrorDetails(field_errors=field_errors),
            request_id=request_id,
        ),
        request_id=request_id,
    )


def _detail_message(detail: object) -> str:
    """A raise site's ``detail`` rendered as prose, whatever shape it arrived in."""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        message = detail.get("message") or detail.get("detail")
        if isinstance(message, str):
            return message
    return str(detail)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Every ``HTTPException`` raise site, mapped into the envelope with its status kept.

    The status carries the code, because that is what the raise site actually decided. A 423 is
    additionally marked retryable: the write gate's whole point is that the caller should try
    again, and a client cannot infer that from a sentence.
    """
    assert isinstance(exc, StarletteHTTPException | HTTPException)
    request_id = request_id_of(request)
    code: ErrorCode = status_error_code(exc.status_code)
    message = _detail_message(exc.detail)
    details = (
        DenialDetails(reason_code=code, retryable=exc.status_code == _RETRYABLE_STATUS)
        if code in ("forbidden", "write_rejected")
        else None
    )
    return _envelope(
        exc.status_code,
        ErrorBody(code=code, message=message, details=details, request_id=request_id),
        request_id=request_id,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """A failure nobody anticipated. Logged in full, disclosed as nothing.

    The exception's text is never in the body: it is the one place where a stack-trace fragment,
    a file path or a fragment of confidential content would be handed to whoever asked.
    """
    request_id = request_id_of(request)
    logger.exception(
        "Unhandled exception request_id=%s method=%s path=%s",
        request_id, request.method, request.url.path,
    )
    return _envelope(
        500,
        ErrorBody(
            code="internal_error",
            message="The request could not be completed.",
            request_id=request_id,
        ),
        request_id=request_id,
    )


def install_error_contracts(app: FastAPI) -> None:
    """Register the request-id middleware and all three handlers on the application."""
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
