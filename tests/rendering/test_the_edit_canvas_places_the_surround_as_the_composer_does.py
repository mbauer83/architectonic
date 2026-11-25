"""The title and the legend of a diagram being arranged land where the saved picture draws them.

The rule has one owner (`surround_placement`), read by the composer when it draws a laid-out diagram and by
the editor's canvas through the layout surround route. This holds the pair: the geometry read hands over what
was drawn round the diagram and what the diagram occupied; the route is asked with where the diagram is now —
read here off the composed picture, which is the arrangement the canvas holds — and every part it moves must
land where the composed picture has it. Over the product's own path: a layout stored by the editor's patch,
the picture and the geometry asked for at the addresses the diagram page asks, with a legend.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.domain.diagrams.layout.geometry import Extent
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rendering.layout.arrangement import label_extent
from src.infrastructure.rendering.layout.plantuml_svg_reader import RenderedDrawing, read_rendered_drawing
from src.infrastructure.rendering.layout.svg_markup import drawn_extent
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")

#: The reader asks for the legend, which PlantUML draws below the diagram.
_LEGEND = {"legend": "true"}

#: Where the editor's patch moves one node: well right of and below where PlantUML drew it, so the diagram grows
#: and what is drawn round it has to move.
_MOVED_TO = {"x": 1400, "y": 900}

#: How far a part may land from where the composed picture draws it: the picture's written precision.
_LANDED = 0.5


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> RenderedModel:
    return build_rendered_model(tmp_path_factory.mktemp("surround"))


@pytest.fixture
def client(model: RenderedModel) -> Iterator[TestClient]:
    s.init_state(ArtifactRepository(shared_artifact_index([model.repo])), model.repo, None)
    try:
        with TestClient(build_api_app(diagrams_router)) as served:
            yield served
    finally:
        reset_state_for_test()


def _box(extent: Extent) -> dict[str, float]:
    return {"left": extent.left, "top": extent.top, "right": extent.right, "bottom": extent.bottom}


def _now(drawing: RenderedDrawing) -> dict[str, object]:
    """Where the composed picture has the diagram: its shapes, its lines and their labels, as the canvas holds them."""
    picture = drawing.picture
    return {
        "shapes": [_box(shape.extent) for shape in (*picture.elements.values(), *picture.boxes.values())],
        "courses": [[[point.x, point.y] for point in relation.course] for relation in picture.relations],
        "labels": [
            _box(label) for relation in picture.relations if (label := label_extent(relation.words)) is not None
        ],
    }


def test_each_part_lands_where_the_composed_picture_draws_it(model: RenderedModel, client: TestClient) -> None:
    artifact_id = Path(model.scenes["top-to-bottom"].path).stem
    geometry = client.get(f"/api/diagrams/{artifact_id}/layout/geometry", params=_LEGEND).json()
    moved = next(row["key"] for row in geometry["elements"] if row["alias"] == model.alias("broker"))
    patched = client.patch(
        f"/api/diagrams/{artifact_id}/layout",
        json={"patch": {"elements": {moved: {"value": _MOVED_TO, "based_on": None}}}, "dry_run": False},
    )
    assert patched.status_code == 200, patched.text

    surround = client.get(f"/api/diagrams/{artifact_id}/layout/geometry", params=_LEGEND).json()["surround"]
    composed = read_rendered_drawing(client.get(f"/api/diagrams/{artifact_id}/svg", params=_LEGEND).text)
    assert isinstance(composed, RenderedDrawing), composed
    drawn_round = [extent for part in composed.chrome if (extent := drawn_extent(part)) is not None]
    assert surround["parts"] and len(drawn_round) == len(surround["parts"])

    placed = client.post(
        f"/api/diagrams/{artifact_id}/layout/surround/preview",
        json={"drawn": surround["drawn"], "parts": [part["extent"] for part in surround["parts"]], **_now(composed)},
    )
    assert placed.status_code == 200, placed.text
    moves = placed.json()["moves"]

    assert any(abs(dx) + abs(dy) > 1 for dx, dy in moves), moves
    for part, (dx, dy), landed in zip(surround["parts"], moves, drawn_round, strict=True):
        extent = part["extent"]
        assert (extent["left"] + dx, extent["top"] + dy) == pytest.approx((landed.left, landed.top), abs=_LANDED)


def test_a_diagram_not_moved_moves_nothing_round_it(model: RenderedModel, client: TestClient) -> None:
    artifact_id = Path(model.scenes["type-boxes"].path).stem
    surround = client.get(f"/api/diagrams/{artifact_id}/layout/geometry", params=_LEGEND).json()["surround"]
    drawing = read_rendered_drawing(client.get(f"/api/diagrams/{artifact_id}/svg", params=_LEGEND).text)
    assert isinstance(drawing, RenderedDrawing), drawing

    placed = client.post(
        f"/api/diagrams/{artifact_id}/layout/surround/preview",
        json={"drawn": surround["drawn"], "parts": [part["extent"] for part in surround["parts"]], **_now(drawing)},
    ).json()

    assert all(abs(dx) < _LANDED and abs(dy) < _LANDED for dx, dy in placed["moves"]), placed
