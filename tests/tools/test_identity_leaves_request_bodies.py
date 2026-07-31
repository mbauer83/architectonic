"""Identity is removed from request bodies, and an extra field is rejected rather than ignored.

The plan's own framing: the regression is "an extra identity field is rejected", not a mismatch test
over a field that should not exist. Both halves matter.

* Removing ``artifact_id`` from an edit body is what makes the path the single place a caller says
  which entity they mean. With it in both, nothing decides which wins when they disagree.
* ``extra="forbid"`` is what turns the removal into a *contract*. Without it a client that kept
  sending the old body would be silently editing whatever the path named, which is the failure this
  migration is supposed to make impossible — and it would look like success.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.contracts.error_responses import install_error_contracts
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.entities import router as entities_router

TARGET_ID = "REQ@1000000901.IdBody.identity-in-the-path"
OTHER_ID = "REQ@1000000902.IdBody.the-other-one"


def _requirement(artifact_id: str, name: str) -> str:
    return f"""---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

A requirement used to prove identity comes from the path.
"""


@pytest.fixture
def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    from starlette.testclient import TestClient

    root = tmp_path / "engagements" / "ENG-IDBODY" / "architecture-repository"
    directory = root / "projects" / "p" / "model" / "motivation" / "requirement"
    directory.mkdir(parents=True)
    (directory / f"{TARGET_ID}.md").write_text(_requirement(TARGET_ID, "Target"), encoding="utf-8")
    (directory / f"{OTHER_ID}.md").write_text(_requirement(OTHER_ID, "Other"), encoding="utf-8")
    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    app = FastAPI(redirect_slashes=False)
    # Configured as the real application is, so the refusal is asserted in the shape a client
    # actually receives rather than in FastAPI's default.
    install_error_contracts(app)
    app.include_router(entities_router)
    return TestClient(app, raise_server_exceptions=False)


def test_an_edit_body_repeating_the_identity_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    """422, not "ignored" and not "the body wins". A caller sending both has a bug, and the only
    answer that surfaces it is a refusal."""
    response = client.patch(
        f"/api/entities/{TARGET_ID}",
        json={"artifact_id": TARGET_ID, "name": "Renamed", "dry_run": True},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "validation_error"
    assert any(
        error["field"].endswith("artifact_id") for error in detail["details"]["field_errors"]
    ), detail


def test_an_edit_body_naming_a_different_entity_cannot_redirect_the_write(client) -> None:  # type: ignore[no-untyped-def]
    """The failure the removal prevents, stated as its own case: if the body were still accepted,
    this request would edit ``OTHER_ID`` while its URL says ``TARGET_ID``."""
    response = client.patch(
        f"/api/entities/{TARGET_ID}",
        json={"artifact_id": OTHER_ID, "name": "Hijacked", "dry_run": True},
    )

    assert response.status_code == 422


def test_an_edit_without_the_identity_field_addresses_the_path(client) -> None:  # type: ignore[no-untyped-def]
    """The path names the entity, and the write lands on it.

    Asserted on the rename-stable stem, not the whole id: a rename moves the slug, so the returned
    id legitimately differs from the requested one in its tail and agrees in its identity."""
    from src.domain.artifact_id import stable_id

    response = client.patch(f"/api/entities/{TARGET_ID}", json={"name": "Renamed", "dry_run": True})

    assert response.status_code == 200
    assert stable_id(response.json()["artifact_id"]) == stable_id(TARGET_ID)


def test_a_create_body_carrying_an_identity_is_rejected(client) -> None:  # type: ignore[no-untyped-def]
    """A create has no identity to supply — the server mints it. A body that named one would be
    asserting an id the caller has no right to choose."""
    response = client.post(
        "/api/entities",
        json={"artifact_type": "requirement", "name": "Minted", "artifact_id": TARGET_ID},
    )

    assert response.status_code == 422


def test_an_unknown_field_is_rejected_rather_than_dropped(client) -> None:  # type: ignore[no-untyped-def]
    """Same mechanism, the general case: a misspelled field that is silently dropped is a write
    that reports success and did not do what was asked."""
    response = client.patch(
        f"/api/entities/{TARGET_ID}", json={"nmae": "Typo", "dry_run": True}
    )

    assert response.status_code == 422
