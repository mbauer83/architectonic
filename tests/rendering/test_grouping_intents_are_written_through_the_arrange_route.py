"""Grouping intents are written through the arrange route as one diagram edit: the new groupings, the body
drawn for them, and the layout kept matching — a created grouping's box placed on the new picture, a deleted
one's entry dropped. A dry run answers what was compiled and writes nothing."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.artifact_id import stable_id
from src.domain.diagrams.authored_groupings import grouping_ids
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")


@pytest.fixture
def model(rendered_model: RenderedModel) -> RenderedModel:
    return rendered_model


@pytest.fixture
def client(model: RenderedModel) -> Iterator[TestClient]:
    s.init_state(ArtifactRepository(shared_artifact_index([model.repo])), model.repo, None)
    try:
        with TestClient(build_api_app(diagrams_router)) as served:
            yield served
    finally:
        reset_state_for_test()


def _frontmatter(path: Path) -> dict[str, object]:
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def _arrange(client: TestClient, artifact_id: str, intents: list[dict[str, object]], *, dry_run: bool) -> dict:
    answer = client.post(f"/api/diagrams/{artifact_id}/layout/arrange", json={"intents": intents, "dry_run": dry_run})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert not body["errors"], body
    return body


def test_a_created_grouping_is_placed_and_a_deleted_one_is_dropped(model: RenderedModel, client: TestClient) -> None:
    path = Path(model.scenes["groupings"].path)
    artifact_id = path.stem
    orders, billing = stable_id(model.ids["orders"]), stable_id(model.ids["billing"])
    # Taken over first, so the diagram has a layout for the groupings to be kept matching.
    _arrange(client, artifact_id, [{"intent": "align", "keys": [orders, billing], "edge": "top"}], dry_run=False)
    before = _frontmatter(path)
    desk = next(g for g in before["authored-groupings"][0]["groups"])["id"]  # type: ignore[index]
    assert desk in before["layout"]["boxes"]  # type: ignore[index]

    create = [{"intent": "create_grouping", "label": "Applications", "keys": [orders, billing]}]
    dry = _arrange(client, artifact_id, create, dry_run=True)
    (created,) = set(grouping_ids(dry["authored_groupings"])) - set(grouping_ids(before["authored-groupings"]))
    assert dry["wrote"] is False and _frontmatter(path) == before
    assert dry["patch"]["boxes"][created]["value"], "the compiled patch places the new box"

    written = _arrange(client, artifact_id, create, dry_run=False)
    stored = _frontmatter(path)
    assert written["wrote"] is True
    assert set(grouping_ids(stored["authored-groupings"])) == set(grouping_ids(dry["authored_groupings"]))
    assert created in stored["layout"]["boxes"]  # type: ignore[operator]
    assert "Applications" in path.read_text(encoding="utf-8").split("---", 2)[2], "the body draws the new box"

    deleted = _arrange(client, artifact_id, [{"intent": "delete_grouping", "grouping": desk}], dry_run=False)
    stored = _frontmatter(path)
    assert desk not in grouping_ids(stored["authored-groupings"])
    assert desk not in stored["layout"]["boxes"]  # type: ignore[operator]
    assert desk in deleted["patch"]["boxes"] and deleted["patch"]["boxes"][desk].get("value") is None  # removed
    clerk = stable_id(model.ids["clerk"])
    front = stored["authored-groupings"][0]  # type: ignore[index]
    assert clerk in {stable_id(member) for member in front["entity-ids"]}


def test_grouping_intents_leave_a_diagram_plantuml_arranges_without_a_layout(
    model: RenderedModel, client: TestClient,
) -> None:
    path = Path(model.scenes["groupings"].path)
    customer = stable_id(model.ids["customer"])
    _arrange(client, path.stem, [{"intent": "unnest", "keys": [customer]}], dry_run=False)
    stored = _frontmatter(path)
    assert not stored.get("layout")
    front = stored["authored-groupings"][0]  # type: ignore[index]
    assert not front.get("entity-ids") and front["groups"]


def test_an_intent_naming_no_grouping_is_refused_and_nothing_is_written(
    model: RenderedModel, client: TestClient,
) -> None:
    path = Path(model.scenes["groupings"].path)
    before = path.read_text(encoding="utf-8")
    answer = client.post(f"/api/diagrams/{path.stem}/layout/arrange", json={"intents": [
        {"intent": "nest", "keys": [stable_id(model.ids["broker"])], "grouping": "g-nothere"},
    ], "dry_run": False})
    assert answer.status_code == 400 and "no grouping 'g-nothere'" in answer.text
    assert path.read_text(encoding="utf-8") == before
