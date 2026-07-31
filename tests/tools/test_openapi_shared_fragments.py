"""WU-OA1a: the shared OpenAPI infrastructure — error fragments and the base response models
that let types drive the schema."""

from __future__ import annotations

from src.infrastructure.gui.contracts.errors import ErrorEnvelope
from src.infrastructure.gui.routers._openapi import (
    APP_RESPONSES,
    READ_RESPONSES,
    WRITE_RESPONSES,
    OpenMapResponse,
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


def test_write_result_model_carries_the_documented_fields_and_allows_extra() -> None:
    schema = WriteResultResponse.model_json_schema()
    assert {"wrote", "path", "artifact_id"} <= set(schema["properties"])
    # extra="allow" → a handler returning more than the model declares is documented, not
    # filtered: the payload is never altered.
    assert schema.get("additionalProperties") is not False


def test_open_map_response_is_an_object_that_allows_any_field() -> None:
    schema = OpenMapResponse.model_json_schema()
    assert schema["type"] == "object"
    assert schema.get("additionalProperties") is not False
