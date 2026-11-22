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

