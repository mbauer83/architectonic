"""A diagram is arranged through its layout routes: the picture to arrange, and a layout patch.

Over the pictures the product renders (`tests.support.rendered_pictures`). The patch is the write an
editor's Save makes: on a diagram PlantUML arranges it takes the picture over as a first layout, so
one moved element leaves every other where it was drawn; on a laid-out diagram it changes only the
entries it names; and an entry read before someone else changed it is refused, writing nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.application.repo_path_helpers import rendered_path_for
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


def _diagram(model: RenderedModel, scene: str) -> tuple[str, Path]:
    path = Path(model.scenes[scene].path)
    return path.stem, path


def _stored_layout(path: Path) -> object:
    return parse_frontmatter(path.read_text(encoding="utf-8")).get("layout")


def test_the_picture_to_arrange_names_every_element_and_states_no_layout_yet(
    model: RenderedModel, client: TestClient
) -> None:
    artifact_id, _ = _diagram(model, "top-to-bottom")
    answer = client.get(f"/api/diagrams/{artifact_id}/layout/geometry")

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert "layout" not in body
    assert body["elements"] and all(row["key"] for row in body["elements"])
    assert body["relations"]


def test_a_patch_takes_an_automatic_diagram_over_and_moves_only_what_it_names(
    model: RenderedModel, client: TestClient
) -> None:
    artifact_id, path = _diagram(model, "top-to-bottom")
    geometry = client.get(f"/api/diagrams/{artifact_id}/layout/geometry").json()
    moved = geometry["elements"][0]["key"]

    answer = client.patch(
        f"/api/diagrams/{artifact_id}/layout",
        # Read as stating nothing: checked against what the reader read, not the first layout taken over.
        json={"patch": {"elements": {moved: {"value": {"x": 900, "y": 900}, "based_on": None}}}, "dry_run": False},
    )

    assert answer.status_code == 200, answer.text
    layout = answer.json()["layout"]
    assert layout["elements"][moved] == {"x": 900, "y": 900}
    # Taken over whole: every other element is written down where the first layout placed it.
    assert set(layout["elements"]) >= {row["key"] for row in geometry["elements"]}
    stored = _stored_layout(path)
    assert isinstance(stored, dict) and stored["elements"][moved] == {"x": 900, "y": 900}


def test_an_entry_changed_since_it_was_read_is_refused_and_nothing_is_written(
    model: RenderedModel, client: TestClient
) -> None:
    artifact_id, path = _diagram(model, "top-to-bottom")
    key = client.get(f"/api/diagrams/{artifact_id}/layout/geometry").json()["elements"][0]["key"]
    client.patch(
        f"/api/diagrams/{artifact_id}/layout",
        json={"patch": {"elements": {key: {"value": {"x": 10, "y": 10}}}}, "dry_run": False},
    )
    before = path.read_text(encoding="utf-8")

    answer = client.patch(
        f"/api/diagrams/{artifact_id}/layout",
        json={
            "patch": {"elements": {key: {"value": {"x": 20, "y": 20}, "based_on": {"x": 5, "y": 5}}}},
            "dry_run": False,
        },
    )

    assert answer.status_code == 409, answer.text
    assert path.read_text(encoding="utf-8") == before


def test_removing_every_entry_returns_the_diagram_to_plantuml(model: RenderedModel, client: TestClient) -> None:
    artifact_id, path = _diagram(model, "top-to-bottom")
    key = client.get(f"/api/diagrams/{artifact_id}/layout/geometry").json()["elements"][0]["key"]
    layout = client.patch(
        f"/api/diagrams/{artifact_id}/layout",
        json={"patch": {"elements": {key: {"value": {"x": 10, "y": 10}}}}, "dry_run": False},
    ).json()["layout"]

    removal = {section: dict.fromkeys(entries) for section, entries in layout.items() if isinstance(entries, dict)}
    answer = client.patch(f"/api/diagrams/{artifact_id}/layout", json={"patch": removal, "dry_run": False})

    assert answer.status_code == 200, answer.text
    assert answer.json()["layout"] == {}
    assert not _stored_layout(path)


def test_a_member_removed_with_a_layout_patch_is_written_once_and_the_layout_matches_the_body(
    model: RenderedModel, client: TestClient
) -> None:
    artifact_id, path = _diagram(model, "top-to-bottom")
    keys = [row["key"] for row in client.get(f"/api/diagrams/{artifact_id}/layout/geometry").json()["elements"]]
    client.patch(
        f"/api/diagrams/{artifact_id}/layout",
        json={"patch": {"elements": {keys[0]: {"value": {"x": 10, "y": 10}}}}, "dry_run": False},
    )
    detail = client.get(f"/api/diagrams/{artifact_id}").json()
    gone = next(id_ for id_ in detail["entity_ids_used"] if id_.startswith(keys[1]))

    answer = client.put(f"/api/diagrams/{artifact_id}", json={
        "diagram_type": detail["diagram_type"], "name": detail["name"],
        "entity_ids": [id_ for id_ in detail["entity_ids_used"] if id_ != gone],
        "connection_ids": [id_ for id_ in detail.get("connection_ids_used", []) if gone not in id_],
        "layout_patch": {"elements": {keys[0]: {"value": {"x": 40, "y": 40}, "based_on": {"x": 10, "y": 10}}}},
        "dry_run": False,
    })

    assert answer.status_code == 200, answer.text
    stored = _stored_layout(path)
    assert isinstance(stored, dict)
    # The patched entry is written, the removed member's entry goes with it, the rest stay placed.
    assert stored["elements"][keys[0]] == {"x": 40, "y": 40}
    assert keys[1] not in stored["elements"]
    assert set(stored["elements"]) >= set(keys[2:])



def test_preview_draws_proposed_members_under_layout_keys_without_writing(model: RenderedModel, client: TestClient):
    artifact_id, path = _diagram(model, "top-to-bottom")
    before = path.read_bytes()
    existing = model.ids["clerk"]
    proposed = "ROL@1790000000.abc12"
    relation = f"{existing}---{proposed}@@archimate-association"
    answer = client.post(f"/api/diagrams/{artifact_id}/layout/geometry/preview", json={
        "diagram_type": "archimate-layered", "name": "Preview", "entity_ids": [existing], "connection_ids": [],
        "proposed_elements": [{"artifact_id": proposed, "name": "Draft clerk"}],
        "proposed_relations": [{"artifact_id": relation}],
    })
    assert answer.status_code == 200, answer.text
    picture = answer.json()
    assert any(row["key"] == proposed for row in picture["elements"])
    assert len(picture["relations"]) == 1 and picture["relations"][0]["key"]
    assert path.read_bytes() == before
    assert s.get_repo().get_entity(proposed) is None


def test_canvas_commands_and_membership_publish_together(model: RenderedModel, client: TestClient):
    artifact_id, path = _diagram(model, "top-to-bottom")
    before = path.read_bytes()
    proposed = "ROL@1790000000.CaNvAs.dispatcher"
    detail = client.get(f"/api/diagrams/{artifact_id}").json()
    body = {
        "diagram_type": detail["diagram_type"], "name": detail["name"],
        "entity_ids": [*detail["entity_ids_used"], proposed], "connection_ids": detail["connection_ids_used"],
        "commands": [{"op": "model.element.create", "artifact_id": proposed, "name": "Dispatcher",
                      "group": "uncategorized", "summary": "Coordinates dispatch."}],
        "layout_patch": {}, "dry_run": False,
    }
    refused = client.put(f"/api/diagrams/{artifact_id}", json={
        **body, "layout_patch": {"elements": {"missing": {"value": {"x": "invalid", "y": 1}}}},
    })
    assert refused.status_code == 400, refused.text
    assert not list(model.repo.rglob(f"{proposed}.md"))
    assert path.read_bytes() == before
    for dry_run in (True, False):
        answer = client.put(f"/api/diagrams/{artifact_id}", json={**body, "dry_run": dry_run})
        assert answer.status_code == 200, answer.text
        assert answer.json()["wrote"] is not dry_run
        assert bool(list(model.repo.rglob(f"{proposed}.md"))) is not dry_run
    assert "Dispatcher" in rendered_path_for(path, model.repo, ".svg").read_text()
    assert rendered_path_for(path, model.repo, ".png").read_bytes().startswith(b"\x89PNG")
    assert proposed in client.get(f"/api/diagrams/{artifact_id}").json()["entity_ids_used"]


def test_membership_write_with_a_stale_layout_answers_conflict(model: RenderedModel, client: TestClient):
    artifact_id, path = _diagram(model, "top-to-bottom")
    before = path.read_bytes()
    detail = client.get(f"/api/diagrams/{artifact_id}").json()
    result = client.put(f"/api/diagrams/{artifact_id}", json={
        "diagram_type": detail["diagram_type"], "name": detail["name"], "entity_ids": detail["entity_ids_used"],
        "connection_ids": [], "dry_run": False, "layout_patch": {"elements": {
            model.ids["clerk"]: {"value": {"x": 30, "y": 40}, "based_on": {"x": 10, "y": 10}},
        }},
    })
    assert result.status_code == 409, result.text
    assert path.read_bytes() == before


def test_preview_replaces_a_selected_relations_annotations_without_writing(model: RenderedModel, client: TestClient):
    diagram, _ = _diagram(model, "top-to-bottom")
    source, target = model.ids["customer"], model.ids["clerk"]
    key = f"{source}---{target}@@archimate-assignment"
    before = s.get_repo().get_connection(key)
    assert before is not None
    result = client.post(f"/api/diagrams/{diagram}/layout/geometry/preview", json={
        "diagram_type": "archimate-layered", "name": "Edit relation", "entity_ids": [source, target],
        "connection_ids": [key], "proposed_relations": [{"artifact_id": key, "description": "Preview only"}],
        "diagram_entities": {"_connections": [{"artifact_id": key, "include_description": True}]},
    })
    assert result.status_code == 200, result.text
    [line] = result.json()["relations"]
    assert "Preview only" in line["label"]
    assert s.get_repo().get_connection(key) == before
