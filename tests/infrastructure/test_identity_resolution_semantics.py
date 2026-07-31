"""How an identifier in a URL resolves, asserted as behaviour.

Every case here was measured against the real ASGI stack before it was decided, because two of the
seven answers were *not* what the framework gave by default: an incomplete detail path resolved as
the collection, and a repeated scalar query parameter silently kept the last value.

The remaining five are the framework's behaviour, and they are pinned rather than assumed — ``%2E``
in particular decides whether an identifier has one URL spelling or two, which is the difference
between one cache key and two for the same resource.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

from src.infrastructure.gui.contracts.error_responses import install_error_contracts
from src.infrastructure.gui.contracts.identity_resolution import (
    reject_repeated_scalar_query_parameters,
)


@pytest.fixture
def client() -> TestClient:
    """A probe surface configured exactly as the real application is."""
    from fastapi import Depends

    app = FastAPI(
        redirect_slashes=False,
        dependencies=[Depends(reject_repeated_scalar_query_parameters)],
    )
    install_error_contracts(app)

    known = "APP@1712870400.abc123.thing"

    @app.get("/api/things")
    def collection(kind: str | None = None) -> dict[str, object]:
        return {"kind": kind}

    @app.get("/api/things/{artifact_id}")
    def detail(artifact_id: str) -> dict[str, str]:
        from fastapi import HTTPException

        if artifact_id != known:
            raise HTTPException(404, "Not found")
        return {"artifact_id": artifact_id}

    @app.get("/api/things/{artifact_id}/echo")
    def echo(artifact_id: str) -> dict[str, str]:
        return {"artifact_id": artifact_id}

    @app.get("/api/multi")
    def multi(tag: list[str] | None = Query(default=None)) -> dict[str, object]:
        return {"tag": tag}

    return TestClient(app, raise_server_exceptions=False)


KNOWN_ID = "APP@1712870400.abc123.thing"


def test_an_exact_collection_path_resolves_as_the_collection(client: TestClient) -> None:
    assert client.get("/api/things").status_code == 200


def test_a_detail_path_with_the_identifier_omitted_is_not_the_collection(
    client: TestClient,
) -> None:
    """The framework's default was a redirect to the collection, which answers a different
    question than the one asked and hides the caller's bug."""
    response = client.get("/api/things/", follow_redirects=False)
    assert response.status_code == 404


def test_an_unknown_identifier_is_not_distinguishable_from_a_malformed_one(
    client: TestClient,
) -> None:
    """Both 404. A different status for a malformed id would tell a reader which of two ids is
    *shaped* like a real one, which on the assurance surface is a disclosure."""
    unknown = client.get("/api/things/APP@1712870400.zzzzzz.absent")
    malformed = client.get("/api/things/not-an-identifier")
    assert unknown.status_code == malformed.status_code == 404


def test_a_repeated_scalar_query_parameter_is_a_typed_422(client: TestClient) -> None:
    """Not the last value. ``?kind=a&kind=b`` asks for two things through a parameter that names
    one; discarding the first with no signal is how a GUI shows data for the wrong artifact."""
    response = client.get("/api/things?kind=a&kind=b")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "validation_error"
    assert [error["field"] for error in detail["details"]["field_errors"]] == ["query.kind"]


def test_a_repeated_parameter_declared_to_repeat_is_accepted(client: TestClient) -> None:
    """The rule is about *single-valued* parameters. A parameter typed as a sequence means what it
    says, and rejecting it would be the same mistake in the other direction."""
    response = client.get("/api/multi?tag=a&tag=b")
    assert response.status_code == 200
    assert response.json()["tag"] == ["a", "b"]


def test_a_percent_encoded_hash_is_accepted_and_reaches_the_handler_intact(
    client: TestClient,
) -> None:
    """A diagram-local id contains ``#``. Sent raw, a browser treats it as a fragment and never
    sends the tail, so the server sees a request for the host diagram instead."""
    response = client.get("/api/things/DATATY%401782085920.9Nrbqf.model%23Order/echo")
    assert response.status_code == 200
    assert response.json()["artifact_id"] == "DATATY@1782085920.9Nrbqf.model#Order"


def test_a_percent_encoded_slash_is_rejected(client: TestClient) -> None:
    """Slash is outside the identifier grammar, so an identifier containing one is malformed
    rather than a deeper path — which is why a ``purl``-shaped id stays a query parameter."""
    assert client.get("/api/things/pkg%3Anpm%2Fleft-pad/echo").status_code == 404


def test_a_percent_encoded_dot_is_decoded_back_to_a_dot(client: TestClient) -> None:
    """So builders must NOT encode it: ASGI decodes ``%2E``, which means the two spellings name
    one resource through two URLs — two cache keys, one answer."""
    response = client.get("/api/things/APP%401712870400.abc123%2Ething")
    assert response.status_code == 200
    assert response.json()["artifact_id"] == KNOWN_ID
