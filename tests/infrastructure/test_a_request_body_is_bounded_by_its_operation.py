"""A request body larger than its operation reads is refused before it is read (D7)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.infrastructure.backend.cache_directive import directive_for
from src.infrastructure.backend.request_body_limit import RequestBodyLimit
from src.infrastructure.rest.route_policy import DEFAULT_MAX_BODY_BYTES, body_limit_for, row_for_request

ICON_LIMIT = 2 * 1024 * 1024


def _app() -> TestClient:
    app = FastAPI()
    read: list[int] = []

    @app.post("/api/icons")
    async def create(request: Request) -> dict[str, int]:
        body = await request.body()
        read.append(len(body))
        return {"read": len(body)}

    app.add_middleware(RequestBodyLimit)
    client = TestClient(app)
    client.read = read  # type: ignore[attr-defined]
    return client


def test_an_upload_within_its_limit_is_read() -> None:
    client = _app()

    response = client.post("/api/icons", content=b"x" * 1000)

    assert response.status_code == 200 and response.json() == {"read": 1000}


def test_a_declared_length_over_the_limit_is_refused_unread_with_the_limit() -> None:
    client = _app()

    response = client.post("/api/icons", content=b"x" * (ICON_LIMIT + 1))

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["code"] == "request_too_large" and detail["details"] == {"max_body_bytes": ICON_LIMIT}
    assert client.read == []  # type: ignore[attr-defined]


def test_a_chunked_body_is_counted_as_it_arrives() -> None:
    client = _app()

    def chunks():
        for _ in range(3):
            yield b"x" * (ICON_LIMIT // 2)

    response = client.post("/api/icons", content=chunks())

    assert response.status_code == 413 and client.read == []  # type: ignore[attr-defined]


def test_an_operation_naming_no_limit_takes_the_default() -> None:
    assert body_limit_for("POST", "/api/icons") == ICON_LIMIT
    assert body_limit_for("PUT", "/api/diagrams/ARC@1.view01") == DEFAULT_MAX_BODY_BYTES
    assert body_limit_for("POST", "/api/no-such-route") == DEFAULT_MAX_BODY_BYTES


def test_a_literal_segment_outranks_a_parameter_and_the_method_decides() -> None:
    preview = row_for_request("POST", "/api/icons/preview")
    read = row_for_request("GET", "/api/icons/ICO@1.mark01")
    edit = row_for_request("PATCH", "/api/icons/ICO@1.mark01")

    assert preview is not None and preview.operation_id == "icons_preview_shown_icons"
    assert read is not None and read.operation_id == "icons_read_icon"
    assert edit is not None and edit.operation_id == "icons_update_icon"


def test_a_write_does_not_borrow_the_cache_directive_of_the_read_at_its_path() -> None:
    assert directive_for("GET", "/api/icons/ICO@1.mark01") == "no-cache"
    assert directive_for("PATCH", "/api/icons/ICO@1.mark01") == "no-store"
