"""A composition carries the nest and unnest intents an editor kept: *Nest in…* into one of the diagram's own
boxes and *Take out* of one. They are compiled by the one grouping compiler as the body is read, so the
picture the editor previews and the diagram the save writes hold the same groupings; an intent that
cannot apply is refused and writes nothing.
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
from src.infrastructure.rest.routers.diagrams._write_bodies import DiagramComposition
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test


def _composition(**fields: object) -> DiagramComposition:
    return DiagramComposition.model_validate({
        "diagram_type": "archimate-layered", "name": "N", "entity_ids": [], "connection_ids": [], **fields,
    })


def test_the_intents_are_applied_to_the_groupings_as_the_body_is_read() -> None:
    body = _composition(
        authored_groupings=[
            {"id": "g-a", "label": "A", "entity-ids": ["APP@1.x", "APP@2.y"]}, {"id": "g-b", "label": "B"},
        ],
        grouping_intents=[{"intent": "nest", "keys": ["APP@1.x"], "grouping": "g-b"}],
    )
    assert body.grouping_intents is None
    holding = {grouping["id"]: grouping.get("entity-ids", []) for grouping in body.authored_groupings or []}
    assert holding["g-b"] == ["APP@1.x"] and "APP@1.x" not in holding["g-a"]
    out = _composition(
        authored_groupings=body.authored_groupings, grouping_intents=[{"intent": "unnest", "keys": ["APP@1.x"]}],
    )
    assert all("APP@1.x" not in grouping.get("entity-ids", []) for grouping in out.authored_groupings or [])


def test_an_intent_that_is_not_a_regrouping_or_names_no_grouping_is_refused() -> None:
    for intents in (
        [{"intent": "create_grouping", "label": "New", "keys": ["APP@1.x"]}],
        [{"intent": "nest", "keys": ["APP@1.x"], "grouping": "g-nowhere"}],
    ):
        with pytest.raises(ValueError):
            _composition(authored_groupings=[{"id": "g-a", "label": "A"}], grouping_intents=intents)


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


@pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")
def test_the_preview_and_the_save_draw_the_element_in_the_box_it_was_nested_in(
    model: RenderedModel, client: TestClient,
) -> None:
    path = Path(model.scenes["groupings"].path)
    artifact_id = path.stem
    detail = client.get(f"/api/diagrams/{artifact_id}").json()
    [front] = detail["authored_groupings"]
    [desk] = front["groups"]
    orders = model.ids["orders"]
    body = {
        "diagram_type": detail["diagram_type"], "name": detail["name"],
        "entity_ids": detail["entity_ids_used"], "connection_ids": detail["connection_ids_used"],
        "authored_groupings": detail["authored_groupings"],
        "grouping_intents": [{"intent": "nest", "keys": [orders], "grouping": desk["id"]}],
    }

    preview = client.post(f"/api/diagrams/{artifact_id}/layout/geometry/preview", json=body)
    assert preview.status_code == 200, preview.text
    picture = preview.json()
    boxes = {box["alias"]: box for box in picture["boxes"]}
    [drawn] = [one for one in picture["elements"] if one["key"] == stable_id(orders)]
    assert boxes[drawn["inside"]]["key"] == desk["id"]

    saved = client.put(f"/api/diagrams/{artifact_id}", json={**body, "layout_patch": {}, "dry_run": False})
    assert saved.status_code == 200, saved.text
    [stored] = parse_frontmatter(path.read_text(encoding="utf-8"))["authored-groupings"]
    assert any(stable_id(key) == stable_id(orders) for key in stored["groups"][0]["entity-ids"])
