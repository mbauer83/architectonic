"""A canvas save never discards what a diagram's body draws by hand (ADR@1783406738: the diagram owns its body).

Adding one element on the canvas of a diagram whose body drew its own team boxes replaced the body with the
one its composition generates, and the boxes were gone from the file. A replacement — `PUT /api/diagrams/{id}`
and MCP `artifact_replace_diagram`, the same save — now refuses a body written by hand, naming what it would
lose, unless it gives the body up (`manual_layout: false`). The diagram read says so first, so the editor does
not offer a canvas whose save would be refused. Arranging alone writes the layout block and keeps the body.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.diagram_composition import DiagramReplacement
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.layout_tools import artifact_replace_diagram
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")

TEAM_BOX = 'rectangle "Team / Project A" <<BusinessGrouping>> {'
#: A PlantUML alias as the renderer spells one, a further drawing's or a first: what a reader is never shown.
RAW_ALIAS = re.compile(r"[A-Z]{2,4}_\w+__\d|\b[A-Z]{2,4}_[A-Za-z0-9_-]{6,}\b")


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


def _hand_drawn(model: RenderedModel) -> Path:
    """The generated scene with a team box drawn round the customer by hand, as D02 draws its teams."""
    path = Path(model.scenes["top-to-bottom"].path)
    customer = model.alias("customer")
    lines = path.read_text(encoding="utf-8").splitlines()
    at = next(index for index, line in enumerate(lines) if line.rstrip().endswith(f"as {customer}"))
    lines[at:at + 1] = [TEAM_BOX, lines[at], "}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _new_element(model: RenderedModel) -> str:
    made = mcp.artifact_create_entity(
        artifact_type="business-actor", name="Auditor", summary="Reads the books.", dry_run=False,
        repo_root=str(model.repo),
    )
    assert made["wrote"], made
    return str(made["artifact_id"])


def _with_one_more(detail: dict[str, object], added: str, **stated: object) -> dict[str, object]:
    """What the canvas sends when one element is added from the search panel and saved."""
    entity_ids = detail["entity_ids_used"]
    assert isinstance(entity_ids, list)
    return {
        "diagram_type": detail["diagram_type"], "name": detail["name"],
        "entity_ids": [*entity_ids, added], "connection_ids": detail["connection_ids_used"],
        **({"diagram_entities": detail["diagram_entities"]} if detail.get("diagram_entities") else {}),
        "dry_run": False, **stated,
    }


def test_the_read_says_the_body_is_written_by_hand(model: RenderedModel, client: TestClient) -> None:
    generated = client.get(f"/api/diagrams/{Path(model.scenes['groupings'].path).stem}").json()
    assert "written_by_hand" not in generated

    detail = client.get(f"/api/diagrams/{_hand_drawn(model).stem}").json()

    assert "Team / Project A" in detail["written_by_hand"]
    assert detail["hand_drawn"]["boxes"] == ["Team / Project A"]
    assert not RAW_ALIAS.search(detail["written_by_hand"])


def test_a_rest_canvas_save_is_refused_and_the_body_kept(model: RenderedModel, client: TestClient) -> None:
    path = _hand_drawn(model)
    before = path.read_bytes()
    added = _new_element(model)
    detail = client.get(f"/api/diagrams/{path.stem}").json()

    saved = client.put(f"/api/diagrams/{path.stem}", json=_with_one_more(detail, added))

    assert saved.status_code == 400, saved.text
    error = saved.json()["detail"]
    assert error["message"].startswith(f"Diagram '{path.stem}' has a picture drawn by hand: ")
    assert "Team / Project A" in error["message"]
    assert not RAW_ALIAS.search(error["message"])
    assert error["details"]["field_errors"][0]["field"] == "manual_layout"
    assert path.read_bytes() == before


def test_an_mcp_canvas_save_is_refused_and_the_body_kept(model: RenderedModel) -> None:
    path = _hand_drawn(model)
    before = path.read_bytes()
    added = _new_element(model)
    fm = parse_frontmatter(before.decode("utf-8"))
    replacement = DiagramReplacement.model_validate({
        "diagram_type": fm["diagram-type"], "name": fm["name"],
        "entity_ids": [*fm["entity-ids-used"], added], "connection_ids": fm["connection-ids-used"],
        "dry_run": False,
    })

    with pytest.raises(ValueError, match="Team / Project A"):
        artifact_replace_diagram(artifact_id=path.stem, replacement=replacement, repo_root=str(model.repo))

    assert path.read_bytes() == before


def test_giving_the_body_up_writes_the_generated_one(model: RenderedModel, client: TestClient) -> None:
    path = _hand_drawn(model)
    added = _new_element(model)
    detail = client.get(f"/api/diagrams/{path.stem}").json()

    saved = client.put(f"/api/diagrams/{path.stem}", json=_with_one_more(detail, added, manual_layout=False))

    assert saved.status_code == 200, saved.text
    written = path.read_text(encoding="utf-8")
    assert "Team / Project A" not in written
    assert added in parse_frontmatter(written)["entity-ids-used"]


def test_arranging_alone_keeps_the_hand_drawn_body(model: RenderedModel, client: TestClient) -> None:
    path = _hand_drawn(model)
    geometry = client.get(f"/api/diagrams/{path.stem}/layout/geometry").json()
    element = geometry["elements"][0]
    extent = element["extent"]

    moved = client.patch(f"/api/diagrams/{path.stem}/layout", json={"patch": {"elements": {
        element["key"]: {"value": {"x": round(extent["left"]) + 40, "y": round(extent["top"]) + 40}, "based_on": None},
    }}, "dry_run": False})

    assert moved.status_code == 200, moved.text
    assert TEAM_BOX in path.read_text(encoding="utf-8")
