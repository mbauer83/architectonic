"""A canvas save keeps the diagram's viewpoint unless it says otherwise.

The canvas save (`PUT /api/diagrams/{id}`, and MCP's same save) passed an omitted `viewpoint` on as
`None`, which `edit_diagram` reads as "clear it" — so every canvas save of a diagram with a viewpoint
dropped the viewpoint. Omitted now keeps it, as an omitted layout does; an explicit `null` still clears it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")

_VIEWPOINT = {"slug": "layered", "version": 1}


@pytest.fixture
def client(rendered_model: RenderedModel) -> Iterator[TestClient]:
    s.init_state(ArtifactRepository(shared_artifact_index([rendered_model.repo])), rendered_model.repo, None)
    try:
        with TestClient(build_api_app(diagrams_router)) as served:
            yield served
    finally:
        reset_state_for_test()


def _save(client: TestClient, model: RenderedModel, **extra: object):
    artifact_id = Path(model.scenes["top-to-bottom"].path).stem
    detail = client.get(f"/api/diagrams/{artifact_id}").json()
    return client.put(f"/api/diagrams/{artifact_id}", json={
        "diagram_type": detail["diagram_type"], "name": detail["name"],
        "entity_ids": detail["entity_ids_used"], "connection_ids": detail["connection_ids_used"],
        "layout_patch": {}, "dry_run": False, **extra,
    })


def _stored_viewpoint(model: RenderedModel) -> object:
    text = Path(model.scenes["top-to-bottom"].path).read_text(encoding="utf-8")
    return parse_frontmatter(text).get("viewpoint")


def test_a_save_that_does_not_mention_the_viewpoint_keeps_it(
    rendered_model: RenderedModel, client: TestClient,
) -> None:
    applied = _save(client, rendered_model, viewpoint=_VIEWPOINT)
    assert applied.status_code == 200, applied.text
    assert _stored_viewpoint(rendered_model) == _VIEWPOINT

    saved = _save(client, rendered_model)
    assert saved.status_code == 200, saved.text
    assert _stored_viewpoint(rendered_model) == _VIEWPOINT


def test_an_explicit_null_still_clears_it(rendered_model: RenderedModel, client: TestClient) -> None:
    assert _save(client, rendered_model, viewpoint=_VIEWPOINT).status_code == 200
    cleared = _save(client, rendered_model, viewpoint=None)
    assert cleared.status_code == 200, cleared.text
    assert _stored_viewpoint(rendered_model) is None
