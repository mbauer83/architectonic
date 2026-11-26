"""The local-operator gate, as the one dependency an operation that requires it declares.

Some operations change what the running process may do rather than what a repository holds — holding a
git credential, authorizing the confidential store. No principal exists to ask, so such an operation is
accepted only as a local operator request (`operator_request`): from the loopback, carrying the operator
header. Each operation's route-policy row says whether it is gated (`RouteRow.gate`); the route declares
`require_local_operator`, and `tests/architecture/test_the_local_operator_gate_is_declared_once.py` holds
the two to each other, so the gate is visible in one place for the per-operation authorization to come.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Header, Request

from src.infrastructure.rest.contracts.errors import ApiError, DenialDetails
from src.infrastructure.rest.contracts.operator_request import OPERATOR_REQUEST_HEADER, is_local_operator_request
from src.infrastructure.rest.routers._openapi import error_response

#: What a gated operation answers a request that is not a local operator request.
LOCAL_OPERATOR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: error_response(
        "The request is not a local operator request: one from the loopback carrying "
        f"`{OPERATOR_REQUEST_HEADER}`, as this backend's GUI and command line send"
    ),
}


def require_local_operator(
    request: Request,
    operator_request: Annotated[
        str | None,
        Header(
            alias=OPERATOR_REQUEST_HEADER,
            description="`1` from the GUI or command line on this machine; any other request is refused",
        ),
    ] = None,
) -> None:
    """Refuse, with 403 `operator_request_required`, a request that is not a local operator request.

    The header is declared so the published document names it; the gate reads the request itself,
    because the loopback condition is a property of the client, not of a parameter.
    """
    del operator_request
    if not is_local_operator_request(request):
        raise ApiError(
            403, "forbidden",
            "This operation is accepted only from the GUI or command line on the machine the backend runs on.",
            DenialDetails(reason_code="operator_request_required"),
        )
