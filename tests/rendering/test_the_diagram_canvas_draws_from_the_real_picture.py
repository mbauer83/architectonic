"""The diagram canvas: drawn from PlantUML's real picture, and its resized shapes by the real composer.

Over the pictures the product renders (`tests.support.rendered_pictures`). What the canvas reads it
reads through the product's own joins, so the tests ask what an editor relies on: every element it
offers to move carries the key a layout names it by, every line knows which stated relation it is and
runs from its source, a grouping's box is addressed by its grouping id — and a shape it resizes is
drawn as the composer draws a stored one.
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
from src.domain.diagrams.authored_groupings import GROUPING_ID_KEY, read_rule_key
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rendering.layout.diagram_geometry import diagram_geometry
from src.infrastructure.rendering.layout.drawing_wire import element_of, node_of
from src.infrastructure.rendering.layout.plantuml_svg_reader import (
    RenderedDrawing,
    read_rendered_drawing,
)
from src.infrastructure.rendering.layout.shape_drawing import fitted_box, resized_element
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
from tests.support.api_app import build_api_app
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available
from tests.support.rest_state import reset_state_for_test

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> RenderedModel:
    return build_rendered_model(tmp_path_factory.mktemp("diagram-canvas"))


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


def test_a_computed_box_says_what_it_admits_and_a_stated_one_does_not(model: RenderedModel) -> None:
    # What the canvas narrows its palette by when something is added inside a box (sketch 03·2).
    computed = _rows(_geometry(model, "type-boxes"), "boxes")
    domains = [row for row in computed if row["kind"] == "domain"]
    types = [row for row in computed if row["kind"] == "type"]

    assert domains and types
    assert all(isinstance(row["rule"], dict) and set(row["rule"]) == {"domain"} for row in domains)
    assert all(isinstance(row["rule"], dict) and set(row["rule"]) == {"type"} for row in types)
    for row in [*domains, *types]:
        innermost = read_rule_key(str(row["key"])).path[-1]
        assert row["rule"] == {innermost.kind: innermost.value}
    stated = _rows(_geometry(model, "groupings"), "boxes")
    assert all(row.get("rule") is None for row in stated if row["kind"] == "authored-grouping")


@pytest.fixture
def client(model: RenderedModel) -> Iterator[TestClient]:
    s.init_state(ArtifactRepository(shared_artifact_index([model.repo])), model.repo, None)
    try:
        with TestClient(build_api_app(diagrams_router)) as client:
            yield client
    finally:
        reset_state_for_test()


def _diagram_id(model: RenderedModel, scene: str) -> str:
    return Path(model.scenes[scene].path).stem


def test_the_geometry_is_served_and_kept_by_no_one(client: TestClient, model: RenderedModel) -> None:
    response = client.get(f"/api/diagrams/{_diagram_id(model, 'top-to-bottom')}/layout/geometry")

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["name"] == "Order handling" and response.json()["elements"]
    assert client.get("/api/diagrams/ARC@1790000000.nowhere/layout/geometry").status_code == 404


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
    """The pair: what the canvas is sent and what it sends back are one drawing, over every scene drawn."""
    for scene in model.scenes.values():
        drawing = read_rendered_drawing(scene.svg)
        assert isinstance(drawing, RenderedDrawing)
        for group in (*drawing.shapes.values(), *(markup.group for markup in drawing.relations)):
            assert _markup(element_of(node_of(group))) == _markup(group)


def test_a_resized_shape_is_drawn_by_the_composer(client: TestClient, model: RenderedModel) -> None:
    scene = "groupings"
    drawing = read_rendered_drawing(model.scenes[scene].svg)
    assert isinstance(drawing, RenderedDrawing)
    alias, box = next(iter(drawing.picture.boxes.items()))
    element_alias, element = next(iter(drawing.picture.elements.items()))
    grown = Extent(box.extent.left, box.extent.top, box.extent.right + 80, box.extent.bottom + 40)
    wider = Extent(element.extent.left, element.extent.top, element.extent.right + 60, element.extent.bottom)

    response = client.post(f"/api/diagrams/{_diagram_id(model, scene)}/layout/preview", json={"shapes": [
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


def test_a_drawing_that_is_not_one_is_refused(client: TestClient, model: RenderedModel) -> None:
    script = {"tag": "script", "attributes": {}, "text": "alert(1)", "children": []}
    extent = {"left": 0, "top": 0, "right": 10, "bottom": 10}

    response = client.post(f"/api/diagrams/{_diagram_id(model, 'groupings')}/layout/preview", json={"shapes": [
        {"drawing": {"tag": "g", "attributes": {}, "text": None, "children": [script]}, "box": True,
         "drawn": extent, "to": extent},
    ]})

    assert response.status_code == 422
    assert "<script>" in response.text


def _wire(extent: Extent) -> dict[str, float]:
    return {"left": extent.left, "top": extent.top, "right": extent.right, "bottom": extent.bottom}


def _words_across(group: Element) -> list[tuple[float, float]]:
    """Where each word of a drawn element's label starts and ends, across."""
    return [
        (float(text.get("x") or 0), float(text.get("x") or 0) + float(text.get("textLength") or 0))
        for text in group.iter() if text.tag.endswith("text") and (text.text or "").strip("  \t\n")
    ]


def test_an_element_sized_to_its_least_width_keeps_every_word_inside_it(model: RenderedModel) -> None:
    """The pair, A-02.08: the least width the canvas is offered (`least_width`) and the label the composer sets
    again at that width (`resized_element`). Over every element of every scene drawn; before, the canvas
    floored a resize at 24 units and the words were drawn across the outline."""
    offered = 0
    for name, scene in model.scenes.items():
        drawing = read_rendered_drawing(scene.svg)
        assert isinstance(drawing, RenderedDrawing)
        rows = {str(row["alias"]): row for row in _rows(_geometry(model, name), "elements")}
        for alias, element in drawing.picture.elements.items():
            least = rows[alias].get("least_width")
            if least is None:
                continue
            offered += 1
            assert isinstance(least, float)
            drawn = element.extent
            narrowest = Extent(drawn.left, drawn.top, drawn.left + least, drawn.bottom)
            for start, end in _words_across(resized_element(drawing.shapes[alias], drawn, narrowest)):
                assert narrowest.left <= start + 0.01 and end <= narrowest.right + 0.01, (name, alias, start, end)
            assert least <= drawn.width + 0.01, (name, alias)
    assert offered > 0
