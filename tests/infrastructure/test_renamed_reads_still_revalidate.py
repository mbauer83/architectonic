"""A renamed cache-eligible read still revalidates with an ETag.

Risk 2, and the reason the eligibility registry had to stop being a list of exact strings. It was
one, and identity has moved into the path: `/api/entities/{artifact_id}` cannot be written as a
literal at all, so the read would have silently stopped serving a validator — no error, no failing
test, just every client re-fetching a body it already held.

Behavioural, through the middleware and the route, because that is the only place the property is
observable: a unit test of the eligibility predicate would pass while the middleware never ran.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from src.infrastructure.rest.routers.entities import router as entities_router
from tests.support.api_app import build_api_app

ENTITY_ID = "REQ@1000000900.EtagRn.revalidation-probe"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    from starlette.testclient import TestClient

    root = tmp_path / "engagements" / "ENG-ETAG" / "architecture-repository"
    _write(
        root / "projects" / "p" / "model" / "motivation" / "requirement" / f"{ENTITY_ID}.md",
        f"""---
artifact-id: {ENTITY_ID}
artifact-type: requirement
name: "Revalidation Probe"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## Revalidation Probe

A requirement whose read must keep serving a validator after the route was renamed.
""",
    )
    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    # The conditional-read middleware is what this module is about, and `build_api_app` installs it
    # in the product's order — inside the cache directive, so a 304 keeps the `no-cache` it chose.
    return TestClient(build_api_app(entities_router))


@pytest.mark.parametrize(
    "url",
    [
        "/api/entities",
        f"/api/entities/{ENTITY_ID}",
        f"/api/entities/{ENTITY_ID}/context",
    ],
)
def test_a_renamed_cache_eligible_read_serves_an_etag(client, url: str) -> None:  # type: ignore[no-untyped-def]
    """Each of these moved in the 0.2.0 rename, and each carried an ETag before it moved."""
    response = client.get(url)
    assert response.status_code == 200, url
    assert response.headers.get("etag"), f"{url} lost its validator in the rename"
    assert response.headers.get("cache-control") == "no-cache", url


@pytest.mark.parametrize(
    "url",
    [
        "/api/entities",
        f"/api/entities/{ENTITY_ID}",
        f"/api/entities/{ENTITY_ID}/context",
    ],
)
def test_the_served_validator_is_accepted_back(client, url: str) -> None:  # type: ignore[no-untyped-def]
    """The property that matters is the round trip: a client holding the answer is told so.

    Serving an ETag nobody honours is the same as serving none, so the second request has to be a
    304 — and a 304 with no body, since re-deriving it is exactly what this saves."""
    tag = client.get(url).headers["etag"]

    revalidated = client.get(url, headers={"If-None-Match": tag})

    assert revalidated.status_code == 304, url
    assert revalidated.content == b""
    assert revalidated.headers["etag"] == tag


def test_a_read_that_is_not_model_derived_still_serves_no_validator(client) -> None:  # type: ignore[no-untyped-def]
    """The registry is an allowlist, and the rename must not have widened it: an attribute schema
    is repository data outside the indexed artifact set, so its generation says nothing about it."""
    response = client.get("/api/entity-schemata/requirement")
    assert response.status_code in (200, 500)
    assert "etag" not in {key.lower() for key in response.headers}
