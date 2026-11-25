"""Layout intents are written through the layout route: compiled to the patch that states them, then the
same write a hand-made patch makes — over the first layout of an automatic diagram, checked, and refused
with the reason where they do not apply."""

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


def _diagram(model: RenderedModel) -> tuple[str, Path]:
    path = Path(model.scenes["top-to-bottom"].path)
    return path.stem, path


def _stored_layout(path: Path) -> object:
    return parse_frontmatter(path.read_text(encoding="utf-8")).get("layout")


def test_align_takes_an_automatic_diagram_over_and_writes_the_compiled_patch(
    model: RenderedModel, client: TestClient,
) -> None:
    artifact_id, path = _diagram(model)
    keys = [row["key"] for row in client.get(f"/api/diagrams/{artifact_id}/layout/geometry").json()["elements"]][:2]
    intents = [{"intent": "align", "keys": keys, "edge": "left"}]

    dry = client.post(f"/api/diagrams/{artifact_id}/layout/arrange", json={"intents": intents})
    assert dry.status_code == 200, dry.text
    assert dry.json()["wrote"] is False and _stored_layout(path) is None

    answer = client.post(f"/api/diagrams/{artifact_id}/layout/arrange", json={"intents": intents, "dry_run": False})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    placed = body["layout"]["elements"]
    assert placed[keys[0]]["x"] == placed[keys[1]]["x"]
    # Read as stating nothing: every compiled entry is checked against an absent stored one, which the
    # answer omits.
    assert body["patch"]["elements"] and all("based_on" not in e for e in body["patch"]["elements"].values())
    assert _stored_layout(path) == body["layout"]


def test_return_to_automatic_hands_the_whole_diagram_back_to_plantuml(model: RenderedModel, client: TestClient) -> None:
    artifact_id, path = _diagram(model)
    keys = [row["key"] for row in client.get(f"/api/diagrams/{artifact_id}/layout/geometry").json()["elements"]][:2]
    client.post(f"/api/diagrams/{artifact_id}/layout/arrange",
                json={"intents": [{"intent": "align", "keys": keys, "edge": "top"}], "dry_run": False})
    assert _stored_layout(path)

    answer = client.post(f"/api/diagrams/{artifact_id}/layout/arrange",
                         json={"intents": [{"intent": "return_to_automatic"}], "dry_run": False})
    assert answer.status_code == 200, answer.text
    assert not answer.json()["layout"] and not _stored_layout(path)


@pytest.mark.parametrize(("intents", "status"), [
    # Not an intent at all: the request schema names the intents there are.
    ([{"intent": "rotate"}], 422),
    ([{"intent": "align", "keys": ["APP@1712870400.nothere", "APP@1712870401.nothere"], "edge": "left"}], 400),
])
def test_an_intent_that_does_not_apply_is_refused_and_nothing_is_written(
    model: RenderedModel, client: TestClient, intents: list[dict[str, object]], status: int,
) -> None:
    artifact_id, path = _diagram(model)
    answer = client.post(f"/api/diagrams/{artifact_id}/layout/arrange", json={"intents": intents, "dry_run": False})
    assert answer.status_code == status, answer.text
    assert _stored_layout(path) is None
