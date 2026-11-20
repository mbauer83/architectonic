"""What the product draws, read back out of the picture: every shape, every relation, where it sits.

The round trip the project asks of a syntax it both writes and reads. The renderer writes a body,
PlantUML draws it, and the reader must find in the picture exactly what the body declared — stated
over each way the notation can draw one model, not over one diagram that happens to work: a
composition drawn as a container, an entity drawn twice, an icon, a specialization line, both
junctions, authored groupings one inside another, type boxes, both directions, and the picture a
reader sees through a lens with its legend drawn in.

The model and its scenes are built by `tests.support.rendered_pictures` with the tools an author
uses. Skipped without plantuml.jar, like every other rendered-picture assertion here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.modeling.binding_normalize import restore_diagram_shorthand
from src.application.puml_alias_declarations import declared_aliases
from src.domain.diagrams.layout.box_aliases import BoxKind
from src.domain.diagrams.layout.picture_checks import KEPT_BY_THE_ROUTER, check_picture
from src.domain.diagrams.layout.rendered_picture import RenderedPicture
from src.domain.repository.frontmatter import parse_frontmatter
from src.infrastructure.mcp.artifact_mcp.context import repo_cached, roots_key
from src.infrastructure.rendering.archimate_occurrences import instance_by_alias
from src.infrastructure.rendering.layout.plantuml_svg_reader import read_rendered_picture
from tests.support.rendered_pictures import (
    SECOND_CLERK,
    RenderedModel,
    build_rendered_model,
    plantuml_available,
)

pytestmark = pytest.mark.skipif(
    not plantuml_available(), reason="plantuml.jar not found — skipping rendered-picture assertions"
)

_SCENES = ("top-to-bottom", "left-to-right", "occurrence", "groupings", "type-boxes", "reading-lens")

#: How far a relation's line may stop short of the shape it ends at. PlantUML ends the line at the
#: base of an end mark, and the longest mark it draws — a hollow triangle — is 18 long.
_END_MARK_REACH = 20.0


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> RenderedModel:
    return build_rendered_model(tmp_path_factory.mktemp("rendered-pictures"))


def _picture(model: RenderedModel, scene: str) -> RenderedPicture:
    read = read_rendered_picture(model.scenes[scene].svg)
    assert isinstance(read, RenderedPicture), f"{scene}: not readable — it holds {read.met}"
    return read


def _arrows_declared(body: str) -> list[str]:
    """The arrow lines of a generated body: its `' Connections` section, up to the first blank line."""
    lines = body.splitlines()
    section = lines[lines.index("' Connections") + 1 :]
    return section[: section.index("")] if "" in section else section


@pytest.mark.parametrize("scene", _SCENES)
class TestEveryScene:
    def test_the_picture_holds_exactly_the_shapes_the_body_declares(self, model: RenderedModel, scene: str) -> None:
        """The pair, asserted: what the writer declared and what the reader found are one set. A
        shape the reader dropped and a shape it invented both fail here."""
        picture = _picture(model, scene)
        declared = {declaration.alias for declaration in declared_aliases(model.scenes[scene].body)}

        assert set(picture.elements) | set(picture.boxes) == declared
        assert not set(picture.elements) & set(picture.boxes)

    def test_the_picture_holds_one_relation_for_each_arrow_drawn(self, model: RenderedModel, scene: str) -> None:
        picture = _picture(model, scene)
        arrows = _arrows_declared(model.scenes[scene].body)

        assert len(picture.relations) == len(arrows)
        for relation in picture.relations:
            first, second = relation.ends
            assert any(first in arrow and second in arrow for arrow in arrows), relation.ends

    def test_every_shape_sits_inside_the_box_it_is_read_as_inside(self, model: RenderedModel, scene: str) -> None:
        picture = _picture(model, scene)

        for shape in (*picture.elements.values(), *picture.boxes.values()):
            assert picture.canvas.encloses(shape.extent), shape.alias
            if shape.inside is not None:
                assert picture.boxes[shape.inside].extent.encloses(shape.extent, slack=2.0), shape.alias

    def test_every_relation_runs_from_its_first_end_to_its_second(self, model: RenderedModel, scene: str) -> None:
        picture = _picture(model, scene)

        for relation in picture.relations:
            first, second = (picture.extent_of(alias) for alias in relation.ends)
            assert first is not None and second is not None
            assert first.distance_to(relation.course[0]) <= _END_MARK_REACH, relation.ends
            assert second.distance_to(relation.course[-1]) <= _END_MARK_REACH, relation.ends
            assert relation.path[0] == relation.course[0] and relation.path[-1] == relation.course[-1]

    def test_every_word_is_measured_and_set_on_the_canvas(self, model: RenderedModel, scene: str) -> None:
        picture = _picture(model, scene)
        labelled = [shape for shape in (*picture.elements.values(), *picture.boxes.values()) if shape.words]

        assert labelled
        for shape in labelled:
            for word in shape.words:
                assert word.width > 0 and word.text == word.text.strip() != ""
                assert picture.canvas.holds(word.start), (shape.alias, word)

    def test_plantuml_s_own_layout_has_none_of_the_decidable_defects(self, model: RenderedModel, scene: str) -> None:
        """The measurement the severity was chosen on, kept as a test: a layout engine places
        these shapes clear of each other and routes around them. If this fails, either the engine
        changed or a check started reporting what is not wrong."""
        found = check_picture(_picture(model, scene)).findings
        assert [finding for finding in found if finding.defect not in KEPT_BY_THE_ROUTER] == []


class TestTheFourKindsOfBox:
    def test_a_composition_is_drawn_as_a_box_that_is_an_element(self, model: RenderedModel) -> None:
        picture = _picture(model, "top-to-bottom")
        instances = {model.alias(nickname) for nickname in model.ids}
        process = picture.boxes[model.alias("process")]

        assert process.kind(element_aliases=instances) is BoxKind.ELEMENT
        assert process.label == "Handle Order"
        parts = {alias for alias, element in picture.elements.items() if element.inside == process.alias}
        assert parts == {model.alias(part) for part in ("check", "ship", "bill", "both", "either")}

    def test_a_domain_box_holds_the_container_and_says_what_it_is(self, model: RenderedModel) -> None:
        picture = _picture(model, "top-to-bottom")
        outer = picture.boxes[picture.boxes[model.alias("process")].inside or ""]

        assert outer.kind(element_aliases=frozenset()) is BoxKind.DOMAIN
        assert list(picture.boxes_around(model.alias("check"))) == [model.alias("process"), outer.alias]

    def test_an_authored_grouping_holds_another_and_is_known_by_its_label(self, model: RenderedModel) -> None:
        picture = _picture(model, "groupings")
        by_label = {box.label: box for box in picture.boxes.values()}
        front, desk = by_label["Front / Office"], by_label["Desk"]

        assert front.kind(element_aliases=frozenset()) is BoxKind.AUTHORED_GROUPING
        assert desk.kind(element_aliases=frozenset()) is BoxKind.AUTHORED_GROUPING
        assert desk.inside == front.alias
        assert picture.elements[model.alias("clerk")].inside == desk.alias
        assert picture.elements[model.alias("customer")].inside == front.alias

    def test_a_type_box_sits_in_its_domain_s_box(self, model: RenderedModel) -> None:
        picture = _picture(model, "type-boxes")
        typed = [box for box in picture.boxes.values() if box.kind(element_aliases=frozenset()) is BoxKind.TYPE]

        assert len(typed) == 1
        assert picture.boxes[typed[0].inside or ""].kind(element_aliases=frozenset()) is BoxKind.DOMAIN
        assert sum(element.inside == typed[0].alias for element in picture.elements.values()) == 3  # noqa: PLR2004


class TestWhatTheNotationDrawsIntoAnElement:
    def test_a_junction_is_a_shape_with_no_words_and_a_relation_may_end_at_it(self, model: RenderedModel) -> None:
        picture = _picture(model, "top-to-bottom")
        both, either = picture.elements[model.alias("both")], picture.elements[model.alias("either")]

        assert (both.words, either.words) == ((), ())
        assert both.extent.width == pytest.approx(both.extent.height)
        assert any(both.alias in relation.ends for relation in picture.relations)
        assert any(either.alias in relation.ends for relation in picture.relations)

    def test_a_specialization_is_a_line_of_its_own_under_the_name(self, model: RenderedModel) -> None:
        clerk = _picture(model, "top-to-bottom").elements[model.alias("clerk")]
        name = next(word for word in clerk.words if word.text == "Clerk")
        specialization = [word for word in clerk.words if word.start.y > name.start.y]

        assert " ".join(word.text for word in specialization) == "«Business Role»"

    def test_an_icon_does_not_stop_the_element_being_read(self, model: RenderedModel) -> None:
        scene = model.scenes["top-to-bottom"]
        assert "<image" in scene.svg, "the scene is meant to draw an icon; without one this test says nothing"

        broker = _picture(model, "top-to-bottom").elements[model.alias("broker")]

        assert broker.label == "Broker"
        assert broker.extent.width > 0 and broker.extent.height > 0

    def test_a_relation_into_a_container_ends_at_the_box(self, model: RenderedModel) -> None:
        picture = _picture(model, "top-to-bottom")
        into_process = [relation for relation in picture.relations if model.alias("process") in relation.ends]

        assert {model.alias("customer"), model.alias("clerk"), model.alias("orders")} <= {
            alias for relation in into_process for alias in relation.ends
        }

    def test_an_end_mark_is_filed_under_the_end_it_sits_at(self, model: RenderedModel) -> None:
        picture = _picture(model, "top-to-bottom")
        marked = [relation for relation in picture.relations if relation.first_marks or relation.second_marks]

        assert marked
        for relation in marked:
            ends = ((relation.first_marks, relation.course[0]), (relation.second_marks, relation.course[-1]))
            for marks, end in ends:
                for mark in marks:
                    assert min(point.distance_to(end) for point in mark.outline) <= _END_MARK_REACH


class TestAnInstanceIsFoundFromItsAlias:
    def test_a_second_drawing_resolves_to_its_occurrence_and_the_first_to_its_entity(
        self, model: RenderedModel
    ) -> None:
        scene = model.scenes["occurrence"]
        picture = _picture(model, "occurrence")
        repo = repo_cached(roots_key([model.repo]))
        entity_by_id = {artifact_id: repo.get_entity(artifact_id) for artifact_id in model.ids.values()}
        stored = parse_frontmatter(Path(scene.path).read_text(encoding="utf-8"))
        # A stored occurrence names its entity in the bindings block; this is the one way back.
        diagram_entities = restore_diagram_shorthand(stored["diagram-entities"], stored["bindings"])

        instances = instance_by_alias(diagram_entities, entity_by_id)

        assert set(picture.elements) <= set(instances) | set(picture.boxes), "every drawn element is an instance"
        clerks = sorted(alias for alias in picture.elements if alias.startswith(model.alias("clerk")))
        assert [instances[alias] for alias in clerks] == [model.ids["clerk"], SECOND_CLERK]
        assert picture.elements[clerks[0]].extent != picture.elements[clerks[1]].extent
        assert picture.boxes[model.alias("process")].kind(element_aliases=instances) is BoxKind.ELEMENT


class TestTheSameModelDrawnOtherwise:
    def test_both_directions_hold_the_same_shapes_laid_out_differently(self, model: RenderedModel) -> None:
        down, across = _picture(model, "top-to-bottom"), _picture(model, "left-to-right")

        assert set(down.elements) == set(across.elements)
        assert set(down.boxes) == set(across.boxes)
        assert down.canvas != across.canvas
        assert {alias: element.inside for alias, element in down.elements.items()} == {
            alias: element.inside for alias, element in across.elements.items()
        }

    def test_a_lens_prints_into_the_label_and_its_legend_is_not_a_shape(self, model: RenderedModel) -> None:
        scene = model.scenes["reading-lens"]
        assert 'class="legend"' in scene.svg, "the scene is meant to draw a legend"
        authored, lensed = _picture(model, "top-to-bottom"), _picture(model, "reading-lens")

        assert set(lensed.elements) == set(authored.elements)
        assert set(lensed.boxes) == set(authored.boxes)
        check = model.alias("check")
        assert lensed.elements[check].label == "Check Stock risk_score: 1"
        assert lensed.elements[check].extent.height > authored.elements[check].extent.height
