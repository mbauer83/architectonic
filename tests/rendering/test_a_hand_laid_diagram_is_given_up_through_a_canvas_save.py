"""A manual-layout diagram's hand-written body is given up through the canvas save: `manual_layout=false` on
`PUT /api/diagrams/{id}` — the same replacement MCP's `artifact_replace_diagram` takes — writes the body the
composition generates and drops the flag, so the diagram can be arranged on its canvas from then on.

The field reached `artifact_edit_diagram` and not the replacement, so the GUI had no way to say it: the
replacement kept the flag whatever it wrote.
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

HAND_WRITTEN = "' laid out by hand"


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


def _replace(client: TestClient, path: Path, **stated: object):
    detail = client.get(f"/api/diagrams/{path.stem}").json()
    return client.put(f"/api/diagrams/{path.stem}", json={
        "diagram_type": detail["diagram_type"], "name": detail["name"],
        "entity_ids": detail["entity_ids_used"], "connection_ids": detail["connection_ids_used"],
        "dry_run": False, **stated,
    })


def test_manual_layout_false_replaces_the_hand_written_body_and_drops_the_flag(
    model: RenderedModel, client: TestClient,
) -> None:
    path = Path(model.scenes["top-to-bottom"].path)
    made = _replace(client, path, manual_layout=True)
    assert made.status_code == 200, made.text
    assert parse_frontmatter(path.read_text(encoding="utf-8")).get("manual-layout") is True
    path.write_text(path.read_text(encoding="utf-8").replace("@enduml", f"{HAND_WRITTEN}\n@enduml"), encoding="utf-8")

    given_up = _replace(client, path, manual_layout=False)

    assert given_up.status_code == 200, given_up.text
    written = path.read_text(encoding="utf-8")
    assert "manual-layout" not in parse_frontmatter(written)
    assert HAND_WRITTEN not in written


def test_a_replacement_that_does_not_say_keeps_the_flag(model: RenderedModel, client: TestClient) -> None:
    path = Path(model.scenes["top-to-bottom"].path)
    assert _replace(client, path, manual_layout=True).status_code == 200
    kept = _replace(client, path)
    assert kept.status_code == 200, kept.text
    assert parse_frontmatter(path.read_text(encoding="utf-8")).get("manual-layout") is True
