"""A diagram that states a layout is drawn from it: PlantUML's own picture, composed again.

Over the pictures the product actually renders (`tests.support.rendered_pictures`): nesting, a second
occurrence, icons, specializations, junctions, type boxes, a reading lens. Each test states what a
reader of the picture would check — where an element is, how big a box is, that the picture still
reads as the diagram — by reading the composed picture back through the one reader of PlantUML's
structure, which is also what the viewer's element map and the picture checks read.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import pytest

from src.application.modeling.diagram_identities import alias_by_instance
from src.application.modeling.diagram_layout_statement import laid_out_diagram, stated_layout
from src.domain.artifact_id import stable_id
from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.picture_checks import PictureDefect, check_picture
from src.domain.diagrams.layout.rendered_picture import RenderedPicture
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rendering.laid_out_rendering import drawn_from_layout
from src.infrastructure.rendering.layout.composer import NotComposed, compose
from src.infrastructure.rendering.layout.plantuml_svg_reader import read_rendered_picture
from src.infrastructure.write.artifact_write.diagram_render import render_diagram_outputs
from tests.support.rendered_pictures import RenderedModel, build_rendered_model, plantuml_available

pytestmark = pytest.mark.skipif(not plantuml_available(), reason="plantuml.jar not found")

_SCENES = ("top-to-bottom", "left-to-right", "occurrence", "groupings", "type-boxes", "reading-lens")

#: How far a re-placed shape may sit from where it was put: the coordinates are written to four places.
_PLACED = 0.01


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> RenderedModel:
    return build_rendered_model(tmp_path_factory.mktemp("laid-out"))


def _frontmatter(model: RenderedModel, scene: str) -> dict[str, object]:
    return dict(parse_frontmatter(Path(model.scenes[scene].path).read_text(encoding="utf-8")))


def _picture(svg: str) -> RenderedPicture:
    picture = read_rendered_picture(svg)
    assert isinstance(picture, RenderedPicture), picture
    return picture


def _harvested(model: RenderedModel, scene: str, **changes: dict[str, int]) -> dict[str, object]:
    """The scene's frontmatter with a layout placing every element where PlantUML drew it, then *changes*."""
    frontmatter, picture = _frontmatter(model, scene), _picture(model.scenes[scene].svg)
    elements: dict[str, dict[str, int]] = {}
    for instance, alias in alias_by_instance(frontmatter).items():
        if alias in picture.elements:
            extent = picture.elements[alias].extent
            elements[instance] = {"x": round(extent.left), "y": round(extent.top)}
    for nickname, change in changes.items():
        elements[_key(model, nickname)].update(change)
    return {**frontmatter, "layout": {"elements": elements}}


def _key(model: RenderedModel, nickname: str) -> str:
    """How a layout names an element: by its stable id."""
    return stable_id(model.ids[nickname])


def _laid_out(frontmatter: dict[str, object]) -> LaidOutDiagram:
    diagram = laid_out_diagram(frontmatter, process_runtime_catalogs().ontology)
    assert diagram is not None
    return diagram


def _composed(model: RenderedModel, scene: str, frontmatter: dict[str, object]) -> RenderedPicture:
    composed = compose(model.scenes[scene].svg, _laid_out(frontmatter))
    assert isinstance(composed, str), composed
    return _picture(composed)


def _near(first: Extent, second: Extent, slack: float) -> bool:
    return all(
        abs(a - b) <= slack
        for a, b in zip(
            (first.left, first.top, first.right, first.bottom), (second.left, second.top, second.right, second.bottom),
            strict=True,
        )
    )


class TestWithoutALayout:
    def test_a_diagram_stating_no_layout_is_drawn_by_plantuml_unchanged(self, model: RenderedModel) -> None:
        svg = model.scenes["groupings"].svg

        assert laid_out_diagram(_frontmatter(model, "groupings"), process_runtime_catalogs().ontology) is None
        assert drawn_from_layout(svg, None) == (svg, [])

    @pytest.mark.parametrize("block", [{}, {"grid": 10}, "not a layout"])
    def test_an_empty_or_unreadable_layout_draws_plantuml_s_arrangement(self, block: object) -> None:
        assert stated_layout({"layout": block}) is None

    def test_a_manual_layout_diagram_keeps_its_hand_written_picture(self) -> None:
        assert stated_layout({"manual-layout": True, "layout": {"elements": {"X@1.a": {"x": 1, "y": 2}}}}) is None


@pytest.mark.parametrize("scene", _SCENES)
def test_a_picture_harvested_and_composed_with_nothing_moved_is_the_same_picture(
    model: RenderedModel, scene: str
) -> None:
    before = _picture(model.scenes[scene].svg)
    after = _composed(model, scene, _harvested(model, scene))

    assert set(after.elements) == set(before.elements)
    assert set(after.boxes) == set(before.boxes)
    assert len(after.relations) == len(before.relations)
    # Rounded to whole pixels where the layout was harvested, and nothing else moved.
    for alias, element in before.elements.items():
        assert _near(after.elements[alias].extent, element.extent, 0.5), alias
    for alias, box in before.boxes.items():
        assert _near(after.boxes[alias].extent, box.extent, 0.5), alias
    assert [relation.ends for relation in after.relations] == [relation.ends for relation in before.relations]
    assert [relation.label for relation in after.relations] == [relation.label for relation in before.relations]


def test_what_the_viewer_s_element_map_reads_is_kept(model: RenderedModel) -> None:
    """The map stamps entity ids from `data-qualified-name`, group ids and link ends; all of it must survive."""
    def identities(svg: str) -> list[tuple[str, ...]]:
        groups = ElementTree.fromstring(svg).iter("{http://www.w3.org/2000/svg}g")
        names = ("class", "id", "data-qualified-name", "data-entity-1", "data-entity-2", "data-link-type")
        return sorted(tuple(group.get(name) or "" for name in names) for group in groups if group.get("class"))

    composed = compose(model.scenes["occurrence"].svg, _laid_out(_harvested(model, "occurrence")))

    assert isinstance(composed, str)
    assert identities(composed) == identities(model.scenes["occurrence"].svg)


class TestMovingAndResizing:
    def test_a_moved_element_is_drawn_where_the_layout_puts_it_and_its_relations_follow(
        self, model: RenderedModel
    ) -> None:
        frontmatter = _harvested(model, "top-to-bottom")
        moved = frontmatter["layout"]["elements"][_key(model, "broker")]  # type: ignore[index]
        moved.update(x=moved["x"] + 400, y=moved["y"] + 60)
        after = _composed(model, "top-to-bottom", frontmatter)
        broker = after.elements[model.alias("broker")].extent

        assert (broker.left, broker.top) == pytest.approx((moved["x"], moved["y"]), abs=_PLACED)
        joined = [relation for relation in after.relations if model.alias("broker") in relation.ends]
        assert joined
        for relation in joined:
            end = relation.course[0] if relation.ends[0] == model.alias("broker") else relation.course[-1]
            assert broker.distance_to(end) < 20  # noqa: PLR2004 — at the border, short of its decoration

    def test_a_resized_element_is_drawn_at_its_size_with_its_label_wrapped_inside_it(
        self, model: RenderedModel
    ) -> None:
        before = _picture(model.scenes["top-to-bottom"].svg).elements[model.alias("customer")].extent
        narrow, tall = round(before.width * 0.55), round(before.height * 2.5)
        after = _composed(
            model, "top-to-bottom", _harvested(model, "top-to-bottom", customer={"w": narrow, "h": tall})
        )
        customer = after.elements[model.alias("customer")]

        assert (customer.extent.width, customer.extent.height) == pytest.approx((narrow, tall), abs=_PLACED)
        assert customer.label.replace(" ", "") == _picture(model.scenes["top-to-bottom"].svg).elements[
            model.alias("customer")
        ].label.replace(" ", "")
        assert not [
            finding for finding in check_picture(after).of(PictureDefect.LABEL_WIDER_THAN_SHAPE)
            if model.alias("customer") in finding.shapes
        ]
        assert len({word.start.y for word in customer.words}) > 1  # wrapped onto more lines than it had room for

    def test_a_box_grows_to_hold_a_member_moved_past_its_edge(self, model: RenderedModel) -> None:
        frontmatter = _harvested(model, "groupings")
        clerk = frontmatter["layout"]["elements"][_key(model, "clerk")]  # type: ignore[index]
        clerk.update(x=clerk["x"] + 300)
        after = _composed(model, "groupings", frontmatter)
        moved = after.elements[model.alias("clerk")].extent

        for box in after.boxes_around(model.alias("clerk")):
            assert after.boxes[box].extent.encloses(moved), box

    def test_a_box_stated_larger_is_drawn_larger_and_one_stated_smaller_is_not_narrowed(
        self, model: RenderedModel
    ) -> None:
        frontmatter = _harvested(model, "groupings")
        stated = frontmatter["authored-groupings"][0]  # type: ignore[index]
        drawn = _picture(model.scenes["groupings"].svg)
        box_alias = next(iter(drawn.boxes_around(model.alias("customer"))))
        was = drawn.boxes[box_alias].extent
        frontmatter["layout"]["boxes"] = {  # type: ignore[index]
            stated["id"]: {"x": round(was.left), "y": round(was.top), "w": round(was.width) + 200, "h": 10},
        }
        grown = _composed(model, "groupings", frontmatter).boxes[box_alias].extent

        assert grown.width == pytest.approx(round(was.width) + 200, abs=1)
        assert grown.height == pytest.approx(was.height, abs=1)


def test_a_picture_that_cannot_be_read_is_drawn_as_plantuml_drew_it_with_a_warning(model: RenderedModel) -> None:
    not_a_picture = "<svg xmlns='http://www.w3.org/2000/svg'/>"
    diagram = _laid_out(_harvested(model, "top-to-bottom"))

    assert isinstance(compose(not_a_picture, diagram), NotComposed)
    drawn, warnings = drawn_from_layout(not_a_picture, diagram)
    assert drawn == not_a_picture
    assert warnings and "automatic arrangement" in warnings[0]


def test_the_stored_picture_follows_the_layout_and_returns_when_it_is_removed(model: RenderedModel) -> None:
    """The forgetful map on the stored SVG and PNG: removing the block gives back PlantUML's picture, byte for byte."""
    path = Path(model.scenes["type-boxes"].path)
    rendered = path.parents[1] / "rendered" / f"{path.stem}.svg"
    diagram_id = str(_frontmatter(model, "type-boxes")["artifact-id"])
    assert not render_diagram_outputs(path, [])
    automatic = rendered.read_bytes()
    layout = _harvested(model, "type-boxes")["layout"]
    first = next(iter(layout["elements"].values()))  # type: ignore[union-attr]
    first.update(x=first["x"] + 250)

    stored = mcp.artifact_edit_diagram(artifact_id=diagram_id, layout=layout, dry_run=False, repo_root=str(model.repo))
    assert stored["wrote"], stored
    laid_out = _picture(rendered.read_text(encoding="utf-8"))
    assert rendered.with_suffix(".png").exists()

    removed = mcp.artifact_edit_diagram(artifact_id=diagram_id, layout={}, dry_run=False, repo_root=str(model.repo))
    assert removed["wrote"], removed
    assert any(element.extent.left == first["x"] for element in laid_out.elements.values())
    assert rendered.read_bytes() == automatic


@pytest.mark.parametrize("scene", _SCENES)
def test_every_decoration_is_drawn_against_the_element_it_belongs_to(model: RenderedModel, scene: str) -> None:
    """An arrowhead once sat 15 px below its element: its frame was read off the hook PlantUML's line
    makes in its last pixels. The frame is now read off the decoration itself and its tip put on the
    port, so no decoration can stand away from its element, wherever the element is moved."""
    frontmatter = _harvested(model, scene)
    for placed in list(frontmatter["layout"]["elements"].values())[::2]:  # type: ignore[union-attr]
        placed["y"] += 30
    after = _composed(model, scene, frontmatter)

    for relation in after.relations:
        for end, marks in ((relation.ends[0], relation.first_marks), (relation.ends[1], relation.second_marks)):
            extent = after.extent_of(end)
            assert extent is not None
            for mark in marks:
                nearest = min(extent.distance_to(point) for point in mark.outline)
                assert nearest <= 1.5, (relation.ends, end, nearest)  # noqa: PLR2004 — a stroke's width
