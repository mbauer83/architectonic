"""WU-OA1a: the shared OpenAPI infrastructure — error fragments and the base response models
that let types drive the schema."""

from __future__ import annotations

from src.infrastructure.rest.contracts.errors import ErrorEnvelope
from src.infrastructure.rest.routers._openapi import (
    APP_RESPONSES,
    READ_RESPONSES,
    WRITE_RESPONSES,
    WriteResultResponse,
)


def test_read_responses_documents_404_as_the_error_envelope() -> None:
    assert 404 in READ_RESPONSES
    assert READ_RESPONSES[404]["model"] is ErrorEnvelope


def test_write_responses_covers_the_gate_and_authorization_statuses() -> None:
    assert set(WRITE_RESPONSES) == {400, 403, 409, 423}
    for body in WRITE_RESPONSES.values():
        assert body["description"]
        assert body["model"] is ErrorEnvelope


def test_application_wide_responses_document_validation_and_internal_failure() -> None:
    """422 and 500 can arise on any operation, so they are declared once on the application
    rather than 161 times — and as the envelope, which is what the handlers return."""
    assert set(APP_RESPONSES) == {422, 500}
    for body in APP_RESPONSES.values():
        assert body["model"] is ErrorEnvelope


def test_write_result_model_is_closed_so_the_contract_it_names_means_something() -> None:
    """It used to allow extra, and that made the manifest name a contract promising nothing.

    ``additionalProperties: true`` says "these fields, and possibly anything else": a client cannot
    rely on the shape, and a fitness function cannot tell a typed mutation response from an untyped
    one — which is why seven operations sat in the untyped-response list while already declaring this
    model. Every mutation returns exactly ``state.write_result_to_dict``, so there was never anything
    extra to keep.
    """
    schema = WriteResultResponse.model_json_schema()
    assert {"wrote", "path", "artifact_id"} <= set(schema["properties"])
    assert schema.get("additionalProperties") is False


def test_every_field_of_a_write_result_is_required_because_every_field_is_sent() -> None:
    """``write_result_to_dict`` emits all six keys unconditionally. A default on any of them would
    publish it as omittable — and the frontend decoder, which requires them, would then be *stricter*
    than the document it is checked against, which is the drift the contract check exists to catch."""
    schema = WriteResultResponse.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"]) == set(WriteResultResponse.model_fields)

