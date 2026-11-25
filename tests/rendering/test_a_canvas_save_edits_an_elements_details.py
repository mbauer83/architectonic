"""A canvas save edits an element's details: *Edit details…* records `model.element.edit` in the session,
and the save writes it with the diagram, in the same staged write as every other canvas command —
through the one entity edit (`edit_entity`), so what the entity form would refuse is refused here too,
and a refused save writes nothing at all.
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
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")


@pytest.fixture
def model(tmp_path: Path) -> RenderedModel:
    return build_rendered_model(tmp_path)


@pytest.fixture
def client(model: RenderedModel) -> Iterator[TestClient]:
    s.init_state(ArtifactRepository(shared_artifact_index([model.repo])), model.repo, None)
    try:
        with TestClient(build_api_app(diagrams_router)) as served:
            yield served
    finally:
        reset_state_for_test()


def _save(client: TestClient, model: RenderedModel, command: dict[str, object], *, dry_run: bool):
    artifact_id = Path(model.scenes["top-to-bottom"].path).stem
    detail = client.get(f"/api/diagrams/{artifact_id}").json()
    return client.put(f"/api/diagrams/{artifact_id}", json={
        "diagram_type": detail["diagram_type"], "name": detail["name"],
        "entity_ids": detail["entity_ids_used"], "connection_ids": detail["connection_ids_used"],
        "commands": [command], "layout_patch": {}, "dry_run": dry_run,
    })


def _entity_file(model: RenderedModel, artifact_id: str) -> Path:
    record = s.get_repo().get_entity(artifact_id)
    assert record is not None
    return record.path


def test_the_details_are_written_with_the_diagram_and_only_what_was_stated(
    model: RenderedModel, client: TestClient,
) -> None:
    clerk = model.ids["clerk"]
    path = _entity_file(model, clerk)
    before = path.read_bytes()
    command = {
        "op": "model.element.edit", "artifact_id": clerk, "summary": "Serves the counter.",
        "keywords": ["front-office", "counter"],
    }

    dry = _save(client, model, command, dry_run=True)
    assert dry.status_code == 200, dry.text
    assert path.read_bytes() == before

    answer = _save(client, model, command, dry_run=False)
    assert answer.status_code == 200, answer.text
    written = path.read_text(encoding="utf-8")
    assert "Serves the counter." in written
    frontmatter = parse_frontmatter(written)
    assert frontmatter.get("keywords") == ["front-office", "counter"]
    # Not stated, so not changed: the name and the status stay as they were.
    was = parse_frontmatter(before.decode("utf-8"))
    assert frontmatter.get("name") == was.get("name")
    assert frontmatter.get("status") == was.get("status")


def test_an_edit_the_entity_form_would_refuse_writes_nothing(model: RenderedModel, client: TestClient) -> None:
    clerk = model.ids["clerk"]
    path = _entity_file(model, clerk)
    diagram = Path(model.scenes["top-to-bottom"].path)
    before, drawn = path.read_bytes(), diagram.read_bytes()
    answer = _save(client, model, {
        "op": "model.element.edit", "artifact_id": clerk, "status": "not-a-status",
    }, dry_run=False)
    assert answer.status_code == 400, answer.text
    assert path.read_bytes() == before
    assert diagram.read_bytes() == drawn
