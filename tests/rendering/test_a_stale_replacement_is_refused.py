"""A whole-diagram replacement over a diagram changed since it was read is refused, naming what changed (G10).

Two sessions saving one diagram kept whichever saved last: the replacement wrote what its caller had read,
over whatever the diagram held by then. The read now answers the diagram's `revision` — the diagram read, the
geometry an editor opens on, and MCP's layout query — and a replacement sending it back as `base_revision` is
refused (409 over REST, an error over MCP) when the diagram is no longer at it. Arranging writes only the
layout, whose entries carry their own `based_on`, so it does not make the arranging session's next save stale.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.diagram_composition import DiagramReplacement
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.layout_tools import artifact_query_diagram_layout, artifact_replace_diagram
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


def _path(model: RenderedModel) -> Path:
    return Path(model.scenes["groupings"].path)


def _new_element(model: RenderedModel, name: str) -> str:
    made = mcp.artifact_create_entity(
        artifact_type="business-actor", name=name, summary=f"{name}.", dry_run=False, repo_root=str(model.repo),
    )
    assert made["wrote"], made
    return str(made["artifact_id"])


def _adding(detail: dict[str, object], added: str, revision: object) -> dict[str, object]:
    entity_ids = detail["entity_ids_used"]
    assert isinstance(entity_ids, list)
    return {
        "diagram_type": detail["diagram_type"], "name": detail["name"],
        "entity_ids": [*entity_ids, added], "connection_ids": detail["connection_ids_used"],
        "authored_groupings": detail["authored_groupings"], "base_revision": revision, "dry_run": False,
    }


def test_the_second_of_two_sessions_is_refused(model: RenderedModel, client: TestClient) -> None:
    path = _path(model)
    first = client.get(f"/api/diagrams/{path.stem}").json()
    second = client.get(f"/api/diagrams/{path.stem}").json()
    assert first["revision"] == second["revision"]
    assert client.get(f"/api/diagrams/{path.stem}/layout/geometry").json()["revision"] == first["revision"]

    added = _new_element(model, "Auditor")
    saved = client.put(f"/api/diagrams/{path.stem}", json=_adding(first, added, first["revision"]))
    assert saved.status_code == 200, saved.text
    after_first = path.read_bytes()

    refused = client.put(
        f"/api/diagrams/{path.stem}", json=_adding(second, _new_element(model, "Clerk Two"), second["revision"]),
    )

    assert refused.status_code == 409, refused.text
    message = refused.json()["detail"]["message"]
    assert "changed since it was read" in message
    assert "what it draws" in message
    assert path.read_bytes() == after_first


def test_arranging_does_not_make_the_next_save_stale(model: RenderedModel, client: TestClient) -> None:
    path = _path(model)
    detail = client.get(f"/api/diagrams/{path.stem}").json()
    element = client.get(f"/api/diagrams/{path.stem}/layout/geometry").json()["elements"][0]
    extent = element["extent"]
    moved = client.patch(f"/api/diagrams/{path.stem}/layout", json={"patch": {"elements": {
        element["key"]: {"value": {"x": round(extent["left"]) + 40, "y": round(extent["top"]) + 40}, "based_on": None},
    }}, "dry_run": False})
    assert moved.status_code == 200, moved.text

    added = _new_element(model, "Auditor")
    saved = client.put(f"/api/diagrams/{path.stem}", json=_adding(detail, added, detail["revision"]))

    assert saved.status_code == 200, saved.text


def test_an_mcp_replacement_over_a_stale_revision_is_refused(model: RenderedModel) -> None:
    path = _path(model)
    read = artifact_query_diagram_layout(path.stem, repo_root=str(model.repo))["revision"]
    fm = parse_frontmatter(path.read_text(encoding="utf-8"))

    def replacement(added: str) -> DiagramReplacement:
        return DiagramReplacement.model_validate({
            "diagram_type": fm["diagram-type"], "name": fm["name"],
            "entity_ids": [*fm["entity-ids-used"], added], "connection_ids": fm["connection-ids-used"],
            "authored_groupings": fm["authored-groupings"], "base_revision": read, "dry_run": False,
        })

    written = artifact_replace_diagram(
        artifact_id=path.stem, replacement=replacement(_new_element(model, "Auditor")), repo_root=str(model.repo),
    )
    assert written["wrote"], written
    after_first = path.read_bytes()

    with pytest.raises(ValueError, match="changed since it was read"):
        artifact_replace_diagram(
            artifact_id=path.stem, replacement=replacement(_new_element(model, "Clerk Two")), repo_root=str(model.repo),
        )
    assert path.read_bytes() == after_first
