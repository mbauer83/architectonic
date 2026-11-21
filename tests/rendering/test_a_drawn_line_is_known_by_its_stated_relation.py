"""Which stated relation a drawn line is: one join, made for the composer and the layout lab alike.

A picture names a line's ends in the renderer's order, which need not be the relation's own, and draws
two relations between one pair as two lines no alias tells apart. The join answers both: the key, and
whether the line runs target-first, matched in order where a pair is drawn twice.
"""

from __future__ import annotations

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Layout
from src.domain.diagrams.layout.rendered_picture import DrawnElement, DrawnRelation, RenderedPicture
from src.infrastructure.rendering.layout.relation_identities import DrawnAs, relation_keys_by_index


def _line(first: str, second: str) -> DrawnRelation:
    path = (Point(0, 0), Point(10, 0))
    return DrawnRelation(ends=(first, second), line_type="dependency", path=path, course=path)


def _picture(*relations: DrawnRelation) -> RenderedPicture:
    elements = {
        alias: DrawnElement(alias, Extent(0, 0, 10, 10), None) for alias in ("A", "B", "C")
    }
    return RenderedPicture(canvas=Extent(0, 0, 100, 100), elements=elements, boxes={}, relations=relations)


def test_a_line_drawn_target_first_is_known_as_turned() -> None:
    picture = _picture(_line("B", "A"), _line("A", "C"))
    diagram = LaidOutDiagram(Layout(), {}, relations={"r1": ("A", "B"), "r2": ("A", "C")})

    assert relation_keys_by_index(picture, diagram) == {0: DrawnAs("r1", True), 1: DrawnAs("r2", False)}


def test_two_relations_between_one_pair_are_matched_in_order() -> None:
    picture = _picture(_line("A", "B"), _line("B", "A"))
    diagram = LaidOutDiagram(Layout(), {}, relations={"first": ("A", "B"), "second": ("A", "B")})

    assert relation_keys_by_index(picture, diagram) == {0: DrawnAs("first", False), 1: DrawnAs("second", True)}


def test_a_line_the_diagram_does_not_state_is_absent() -> None:
    picture = _picture(_line("A", "B"), _line("B", "C"))
    diagram = LaidOutDiagram(Layout(), {}, relations={"r1": ("A", "B")})

    assert relation_keys_by_index(picture, diagram) == {0: DrawnAs("r1", False)}

