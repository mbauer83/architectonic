"""The layout lab: drawn from PlantUML's real picture, composed by the real composer, and absent when off.

Over the pictures the product renders (`tests.support.rendered_pictures`). What the lab reads it reads
through the product's own joins, so the tests ask what a lab user relies on: every element the lab
offers to move carries the key a layout names it by, every line knows which stated relation it is
and runs from its source, a grouping's box is addressed by its grouping id — and a layout the lab
sends back is drawn as the composer draws a stored one.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import pytest
from fastapi.testclient import TestClient

from src.application.artifacts.repository import ArtifactRepository
from src.application.modeling.diagram_identities import alias_by_instance
from src.domain.diagrams.authored_groupings import GROUPING_ID_KEY
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import RenderedPicture
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rendering.layout.plantuml_svg_reader import (
    RenderedDrawing,
    read_rendered_drawing,
    read_rendered_picture,
)
from src.infrastructure.rendering.layout.shape_drawing import fitted_box, resized_element
from src.infrastructure.rest.layout_lab.routes import LAB_PREFIX, install_layout_lab
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams._layout_drawing import element_of, node_of
from src.infrastructure.rest.routers.diagrams._layout_geometry import diagram_geometry
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> RenderedModel:
    return build_rendered_model(tmp_path_factory.mktemp("layout-lab"))


def _frontmatter(model: RenderedModel, scene: str) -> dict[str, object]:
    return dict(parse_frontmatter(Path(model.scenes[scene].path).read_text(encoding="utf-8")))


def _geometry(model: RenderedModel, scene: str) -> dict[str, object]:
    geometry = diagram_geometry(
        model.scenes[scene].svg, _frontmatter(model, scene), process_runtime_catalogs().ontology
    )
    assert isinstance(geometry, dict), geometry
    return geometry


def _rows(geometry: dict[str, object], section: str) -> list[dict[str, object]]:
    rows = geometry[section]
    assert isinstance(rows, list)
    return rows


def _extent(wire: object) -> Extent:
    assert isinstance(wire, dict)
    return Extent(wire["left"], wire["top"], wire["right"], wire["bottom"])


def test_every_element_is_offered_under_the_key_a_layout_names_it_by(model: RenderedModel) -> None:
    scene = "occurrence"
    aliases = alias_by_instance(_frontmatter(model, scene))
    elements = _rows(_geometry(model, scene), "elements")

    assert elements
    assert {row["alias"]: row["key"] for row in elements} == {
        alias: instance for instance, alias in aliases.items() if alias in {row["alias"] for row in elements}
    }


def test_every_line_knows_its_relation_and_runs_from_its_source(model: RenderedModel) -> None:
    geometry = _geometry(model, "top-to-bottom")
    shapes = (*_rows(geometry, "elements"), *_rows(geometry, "boxes"))
    extents = {row["alias"]: _extent(row["extent"]) for row in shapes}
    relations = _rows(geometry, "relations")

    assert relations and all(row["key"] for row in relations)
    for row in relations:
        course = row["course"]
        assert isinstance(course, list) and len(course) >= 2
        start, end = Point(*course[0]), Point(*course[-1])
        source, target = extents[str(row["source"])], extents[str(row["target"])]
        assert source.distance_to(start) <= target.distance_to(start), row
        assert target.distance_to(end) <= source.distance_to(end), row


def test_a_grouping_box_is_addressed_by_its_grouping_id(model: RenderedModel) -> None:
    stated = _frontmatter(model, "groupings")["authored-groupings"]
    assert isinstance(stated, list)
    boxes = _rows(_geometry(model, "groupings"), "boxes")

    grouping_keys = {row["key"] for row in boxes if row["kind"] == "authored-grouping"}
    assert stated[0][GROUPING_ID_KEY] in grouping_keys
    assert all(row["section"] == "boxes" for row in boxes if row["kind"] == "authored-grouping")


@pytest.fixture
def lab(model: RenderedModel, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ARCH_LAYOUT_LAB", "1")
    s.init_state(ArtifactRepository(shared_artifact_index([model.repo])), model.repo, None)
    app = build_api_app(diagrams_router)
    install_layout_lab(app)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        reset_state_for_test()


def _diagram_id(model: RenderedModel, scene: str) -> str:
    return Path(model.scenes[scene].path).stem


def test_the_lab_is_absent_unless_switched_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCH_LAYOUT_LAB", raising=False)
    off = build_api_app()
    install_layout_lab(off)
    monkeypatch.setenv("ARCH_LAYOUT_LAB", "true")
    on = build_api_app()
    install_layout_lab(on)

    assert TestClient(off).get(LAB_PREFIX).status_code == 404
    assert TestClient(on).get(LAB_PREFIX).json() == {"enabled": True}
    # Not part of the REST contract either way: the published document is the same with the lab on.
    assert on.openapi() == off.openapi()


def test_the_geometry_is_served_and_kept_by_no_one(lab: TestClient, model: RenderedModel) -> None:
    response = lab.get(f"/api/diagrams/{_diagram_id(model, 'top-to-bottom')}/layout/geometry")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["name"] == "Order handling" and response.json()["elements"]
    assert lab.get("/api/diagrams/ARC@1790000000.nowhere/layout/geometry").status_code == 404


def test_a_layout_sent_to_the_lab_is_drawn_by_the_composer(lab: TestClient, model: RenderedModel) -> None:
    scene = "top-to-bottom"
    picture = read_rendered_picture(model.scenes[scene].svg)
    assert isinstance(picture, RenderedPicture)
    elements = _rows(_geometry(model, scene), "elements")
    key = next(row["key"] for row in elements if row["alias"] == model.alias("broker"))
    was = picture.elements[model.alias("broker")].extent
    moved = {"x": round(was.left) + 300, "y": round(was.top) + 40}

    response = lab.post(
        f"{LAB_PREFIX}/diagrams/{_diagram_id(model, scene)}/picture", json={"layout": {"elements": {key: moved}}}
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/svg+xml")
    composed = read_rendered_picture(response.text)
    assert isinstance(composed, RenderedPicture)
    now = composed.elements[model.alias("broker")].extent
    assert abs(now.left - moved["x"]) < 0.01 and abs(now.top - moved["y"]) < 0.01


def _markup(element: Element) -> str:
    return ElementTree.tostring(element, encoding="unicode")


def test_every_shape_and_line_is_drawn_with_plantuml_s_own_drawing(model: RenderedModel) -> None:
    scene = "top-to-bottom"
    drawing = read_rendered_drawing(model.scenes[scene].svg)
    assert isinstance(drawing, RenderedDrawing)
    geometry = _geometry(model, scene)

    for row in (*_rows(geometry, "elements"), *_rows(geometry, "boxes")):
        assert _markup(element_of(row["drawing"])) == _markup(drawing.shapes[str(row["alias"])]), row["alias"]
    for row, markup in zip(_rows(geometry, "relations"), drawing.relations, strict=True):
        line = row["drawing"]
        assert isinstance(line, dict)
        assert _markup(element_of(line["group"])) == _markup(markup.group)
        assert _markup(element_of(line["line"])) == _markup(markup.line)
    assert geometry["backdrop"] == [node_of(part) for part in drawing.backdrop]


def test_a_drawing_reads_back_as_the_markup_it_was_written_from(model: RenderedModel) -> None:
    """The pair: what the lab is sent and what it sends back are one drawing, over every scene drawn."""
    for scene in model.scenes.values():
        drawing = read_rendered_drawing(scene.svg)
        assert isinstance(drawing, RenderedDrawing)
        for group in (*drawing.shapes.values(), *(markup.group for markup in drawing.relations)):
            assert _markup(element_of(node_of(group))) == _markup(group)


def test_a_resized_shape_is_drawn_by_the_composer(lab: TestClient, model: RenderedModel) -> None:
    scene = "groupings"
    drawing = read_rendered_drawing(model.scenes[scene].svg)
    assert isinstance(drawing, RenderedDrawing)
    alias, box = next(iter(drawing.picture.boxes.items()))
    element_alias, element = next(iter(drawing.picture.elements.items()))
    grown = Extent(box.extent.left, box.extent.top, box.extent.right + 80, box.extent.bottom + 40)
    wider = Extent(element.extent.left, element.extent.top, element.extent.right + 60, element.extent.bottom)

    response = lab.post(f"/api/diagrams/{_diagram_id(model, scene)}/layout/preview", json={"shapes": [
        {"drawing": node_of(drawing.shapes[alias]), "box": True, "drawn": _wire(box.extent), "to": _wire(grown)},
        {"drawing": node_of(drawing.shapes[element_alias]), "box": False, "drawn": _wire(element.extent),
         "to": _wire(wider)},
    ]})

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    fitted, resized = response.json()["drawings"]
    assert _markup(element_of(fitted)) == _markup(fitted_box(drawing.shapes[alias], box.extent, grown))
    assert _markup(element_of(resized)) == _markup(
        resized_element(drawing.shapes[element_alias], element.extent, wider)
    )


def test_a_drawing_that_is_not_one_is_refused(lab: TestClient, model: RenderedModel) -> None:
    script = {"tag": "script", "attributes": {}, "text": "alert(1)", "children": []}
    extent = {"left": 0, "top": 0, "right": 10, "bottom": 10}

    response = lab.post(f"/api/diagrams/{_diagram_id(model, 'groupings')}/layout/preview", json={"shapes": [
        {"drawing": {"tag": "g", "attributes": {}, "text": None, "children": [script]}, "box": True,
         "drawn": extent, "to": extent},
    ]})

    assert response.status_code == 422
    assert "<script>" in response.text


def _wire(extent: Extent) -> dict[str, float]:
    return {"left": extent.left, "top": extent.top, "right": extent.right, "bottom": extent.bottom}


def test_a_layout_that_is_not_one_is_refused_with_what_is_wrong(lab: TestClient, model: RenderedModel) -> None:
    response = lab.post(
        f"{LAB_PREFIX}/diagrams/{_diagram_id(model, 'top-to-bottom')}/picture",
        json={"layout": {"elements": {"APP@1.a": {"x": 1}}}},
    )

    assert response.status_code == 422
    assert "needs both x and y" in response.text
