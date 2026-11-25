"""A further occurrence added on the canvas round-trips through a save: the editor writes the diagram's
occurrence statement and a layout entry under the occurrence's own id, in one write; reading the diagram
back draws the element twice, the second drawing under its own key, alias and place, and the statement
read back is the one written. Removing it again writes the statement without it, and drops its entry.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.artifact_id import stable_id
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")

AGAIN = "occ-clerk-here-2"


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


def _write(client: TestClient, artifact_id: str, occurrences: list[dict[str, str]], patch: dict[str, object]):
    detail = client.get(f"/api/diagrams/{artifact_id}").json()
    entities = {**(detail.get("diagram_entities") or {}), "occurrence": occurrences}
    return client.put(f"/api/diagrams/{artifact_id}", json={
        "diagram_type": detail["diagram_type"], "name": detail["name"],
        "entity_ids": detail["entity_ids_used"], "connection_ids": detail["connection_ids_used"],
        "diagram_entities": entities, "layout_patch": patch, "dry_run": False,
    })


def test_a_further_drawing_written_with_its_place_is_read_back_as_written(
    model: RenderedModel, client: TestClient,
) -> None:
    path = Path(model.scenes["top-to-bottom"].path)
    artifact_id = path.stem
    clerk = model.ids["clerk"]
    statement = [{"id": AGAIN, "backing_entity_id": clerk}]

    preview = client.post(f"/api/diagrams/{artifact_id}/layout/geometry/preview", json={
        **{key: value for key, value in client.get(f"/api/diagrams/{artifact_id}").json().items()
           if key in ("diagram_type", "name")},
        "entity_ids": client.get(f"/api/diagrams/{artifact_id}").json()["entity_ids_used"],
        "connection_ids": [], "diagram_entities": {"occurrence": statement},
    })
    assert preview.status_code == 200, preview.text
    previewed = {one["key"] for one in preview.json()["elements"]}
    assert {stable_id(clerk), AGAIN} <= previewed

    placed = {"x": 640, "y": 480}
    saved = _write(client, artifact_id, statement, {"elements": {AGAIN: {"value": placed, "based_on": None}}})
    assert saved.status_code == 200, saved.text
    assert saved.json()["wrote"], saved.json()

    # Stored in its canonical form (a binding), and read back as the statement the editor wrote.
    assert client.get(f"/api/diagrams/{artifact_id}").json()["diagram_entities"]["occurrence"] == statement
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert frontmatter["layout"]["elements"][AGAIN] == placed
    picture = client.get(f"/api/diagrams/{artifact_id}/layout/geometry").json()
    drawings = {one["key"]: one for one in picture["elements"]}
    assert drawings[AGAIN]["alias"] != drawings[stable_id(clerk)]["alias"]
    # The picture is PlantUML's; the layout read with it places the further drawing where it was put.
    assert picture["layout"]["elements"][AGAIN] == placed

    removed = _write(client, artifact_id, [], {"elements": {AGAIN: {"value": None, "based_on": placed}}})
    assert removed.status_code == 200, removed.text
    assert removed.json()["wrote"], removed.json()
    assert not (client.get(f"/api/diagrams/{artifact_id}").json().get("diagram_entities") or {}).get("occurrence")
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert AGAIN not in (frontmatter.get("layout") or {}).get("elements", {})
    keys = {one["key"] for one in client.get(f"/api/diagrams/{artifact_id}/layout/geometry").json()["elements"]}
    assert AGAIN not in keys and stable_id(clerk) in keys
