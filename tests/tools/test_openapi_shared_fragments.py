"""WU-OA1a: the shared OpenAPI infrastructure — error fragments and the base response models
that let types drive the schema."""

from __future__ import annotations

from src.infrastructure.gui.routers._openapi import (
    READ_RESPONSES,
    WRITE_RESPONSES,
    OpenMapResponse,
    WriteResultResponse,
)


def test_read_responses_documents_404() -> None:
    assert 404 in READ_RESPONSES
    assert "schema" in READ_RESPONSES[404]["content"]["application/json"]


def test_write_responses_covers_the_gate_and_authorization_statuses() -> None:
    assert set(WRITE_RESPONSES) == {400, 403, 409, 423}
    for body in WRITE_RESPONSES.values():
        assert body["description"]
        assert "schema" in body["content"]["application/json"]


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
