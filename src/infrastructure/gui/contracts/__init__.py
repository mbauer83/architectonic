"""Response and error contracts for the REST delivery surface.

DTOs live here, under the delivery adapter that serves them, because they are the shape of
*this* delivery mechanism — not a layer of their own. They derive from application use-case
outputs; the OpenAPI document is generated from them; the frontend's decoders are verified
against that document. Ownership runs outward, and deriving these from the frontend's decoders
would run it backwards.
"""

from src.infrastructure.gui.contracts.errors import (
    ERROR_DETAIL_TYPES,
    ApiError,
    ErrorBody,
    ErrorCode,
    ErrorDetails,
    ErrorEnvelope,
    FieldError,
    status_error_code,
)

__all__ = [
    "ERROR_DETAIL_TYPES",
    "ApiError",
    "ErrorBody",
    "ErrorCode",
    "ErrorDetails",
    "ErrorEnvelope",
    "FieldError",
    "status_error_code",
]
