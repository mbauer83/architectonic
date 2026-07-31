"""The typed error envelope, asserted behaviourally through the ASGI stack.

Three handlers, one envelope, and a request id on every failure. These are HTTP-level tests
rather than unit tests of the handler functions because the thing that can break is the
*registration*: a handler that is never reached leaves FastAPI's default body in place, and a
unit test of the function would still pass.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.infrastructure.gui.contracts.error_responses import (
    REQUEST_ID_HEADER,
    install_error_contracts,
)
from src.infrastructure.gui.contracts.errors import (
    ERROR_DETAIL_TYPES,
    ApiError,
    MethodMismatchDetails,
    ValidationErrorDetails,
)


@pytest.fixture
def client() -> TestClient:
    """A minimal app carrying the error contracts and one route per failure mode."""
    app = FastAPI()
    install_error_contracts(app)

    @app.get("/typed")
    def typed() -> None:
        raise ApiError(
            409,
            "analysis_method_mismatch",
            "This analysis is an STPA.",
            MethodMismatchDetails(analysis_id="ANL@1.ab", expected_method="FMEA", actual_method="STPA"),
        )

    @app.get("/raised")
    def raised() -> None:
        raise HTTPException(404, "Not found: 'APP@1.ab'")

    @app.get("/gated")
    def gated() -> None:
        raise HTTPException(423, "Write rejected: workspace busy")

    @app.get("/needs-param")
    def needs_param(required: str) -> str:
        return required

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("SECRET: /home/someone/.arch-assurance/store.db")

    return TestClient(app, raise_server_exceptions=False)


def test_a_typed_raise_carries_its_code_and_narrowed_details(client: TestClient) -> None:
    response = client.get("/typed")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "analysis_method_mismatch"
    assert detail["details"] == {
        "analysis_id": "ANL@1.ab", "expected_method": "FMEA", "actual_method": "STPA",
    }
    assert detail["request_id"]


def test_an_ordinary_http_exception_becomes_the_envelope_with_its_status_kept(
    client: TestClient,
) -> None:
    """The regression that matters: without an ``HTTPException`` handler the 114 existing raise
    sites keep returning ``{"detail": "<a sentence>"}`` and the envelope is a fiction."""
    response = client.get("/raised")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "not_found"
    assert detail["message"] == "Not found: 'APP@1.ab'"
    assert detail["details"] is None


def test_a_gate_rejection_is_marked_retryable(client: TestClient) -> None:
    """423 means "try again"; a client cannot infer that by matching on prose."""
    detail = client.get("/gated").json()["detail"]
    assert detail["code"] == "write_rejected"
    assert detail["details"] == {"reason_code": "write_rejected", "retryable": True}


def test_request_validation_moves_field_errors_under_details(client: TestClient) -> None:
    response = client.get("/needs-param")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "validation_error"
    fields = [error["field"] for error in detail["details"]["field_errors"]]
    assert "query.required" in fields


def test_an_unhandled_exception_never_discloses_its_text(client: TestClient) -> None:
    response = client.get("/boom")
    assert response.status_code == 500
    assert "SECRET" not in response.text
    assert ".arch-assurance" not in response.text
    assert response.json()["detail"]["code"] == "internal_error"


@pytest.mark.parametrize("path", ["/typed", "/raised", "/gated", "/needs-param", "/boom"])
def test_every_error_response_is_uncacheable_and_carries_a_request_id(
    client: TestClient, path: str
) -> None:
    """``no-store`` on every error, not only the confidential ones.

    On the assurance surface a cached or revalidatable error would let a reader distinguish an
    above-ceiling id from an absent one. Everywhere else it is simply true: an error body is a
    statement about one moment."""
    response = client.get(path)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers[REQUEST_ID_HEADER]
    assert response.json()["detail"]["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_an_inbound_request_id_is_echoed_rather_than_replaced(client: TestClient) -> None:
    """A caller correlating across a proxy hop supplies the id; overwriting it breaks the trail."""
    response = client.get("/raised", headers={REQUEST_ID_HEADER: "caller-supplied-id"})
    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-id"
    assert response.json()["detail"]["request_id"] == "caller-supplied-id"


def test_a_code_cannot_ship_details_the_contract_does_not_declare() -> None:
    """``details`` is closed per code. Validating at construction is what keeps it closed —
    a check only at serialization time would let the wrong payload reach a response builder."""
    with pytest.raises(ValueError, match="requires MethodMismatchDetails"):
        ApiError(409, "analysis_method_mismatch", "wrong", ValidationErrorDetails(field_errors=[]))
    with pytest.raises(ValueError, match="declares no details"):
        ApiError(404, "not_found", "gone", ValidationErrorDetails(field_errors=[]))
    with pytest.raises(ValueError, match="Undeclared error code"):
        ApiError(400, "not_a_real_code", "nope")  # type: ignore[arg-type]


def test_every_declared_code_has_a_details_decision() -> None:
    """Adding a code means deciding what it carries — including deciding that it carries nothing."""
    from typing import get_args

    from src.infrastructure.gui.contracts.errors import ErrorCode

    assert set(get_args(ErrorCode)) == set(ERROR_DETAIL_TYPES)
