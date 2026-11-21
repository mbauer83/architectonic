"""What the layout lab is given to draw a diagram from: PlantUML's picture of it, read, with its joins made.

Nothing is read here that the product does not already read. The picture comes through the one reader
of PlantUML's structure (`plantuml_svg_reader`); which instance, grouping and stated relation each
shape and line is comes through the joins the composer makes (`diagram_layout_statement`,
`box_identities`, `relation_identities`); a box's title band and an element's outside label are the
text regions the router keeps out of (`text_clearance`). This module only writes those answers down
as plain values a browser can take, so the lab draws exactly what the composer would arrange.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.application.modeling.diagram_layout_statement import DeclaresElementKinds, joined_to_its_picture
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Layout
from src.domain.diagrams.layout.rendered_picture import (
    DrawnBox,
    DrawnElement,
    DrawnRelation,
    MeasuredWord,
    NotReadable,
    RenderedPicture,
)
from src.domain.diagrams.layout.route_quality import square_course
from src.domain.diagrams.layout.text_clearance import padded, text_extent, title_band
from src.infrastructure.rendering.layout.box_identities import box_keys_by_alias
from src.infrastructure.rendering.layout.plantuml_svg_reader import read_rendered_picture
from src.infrastructure.rendering.layout.relation_identities import DrawnAs, relation_keys_by_index

type Wire = dict[str, object]


def _extent(extent: Extent | None) -> Wire | None:
    if extent is None:
        return None
    return {"left": extent.left, "top": extent.top, "right": extent.right, "bottom": extent.bottom}


def _words(words: Sequence[MeasuredWord]) -> list[Wire]:
    return [{"text": word.text, "x": word.start.x, "y": word.start.y, "width": word.width} for word in words]


def _point(point: Point) -> list[float]:
    return [point.x, point.y]


def _element(element: DrawnElement, diagram: LaidOutDiagram) -> Wire:
    label = text_extent(element.words)
    outside = label is not None and not element.extent.encloses(label)
    return {
        "alias": element.alias,
        "key": diagram.instance_by_alias.get(element.alias),
        "label": element.label,
        "extent": _extent(element.extent),
        "inside": element.inside,
        "words": _words(element.words),
        # A label set outside its outline — an actor's, below it — is text a route keeps out of.
        "outside_label": _extent(padded(label)) if outside and label is not None else None,
    }


def _box(box: DrawnBox, diagram: LaidOutDiagram, keys: Mapping[str, str]) -> Wire:
    kind = box.kind(element_aliases=diagram.instance_by_alias)
    instance = diagram.instance_by_alias.get(box.alias)
    title = text_extent(box.words)
    return {
        "alias": box.alias,
        "kind": kind.value,
        # An element holding its parts is placed as an element is; every other box by its box key.
        "section": "elements" if instance is not None else "boxes",
        "key": instance if instance is not None else keys.get(box.alias),
        "label": box.label,
        "extent": _extent(box.extent),
        "inside": box.inside,
        "words": _words(box.words),
        "title_band": _extent(title_band(box.extent, title)) if title is not None else None,
    }


def _relation(index: int, relation: DrawnRelation, drawn_as: DrawnAs | None) -> Wire:
    turned = drawn_as is not None and drawn_as.turned
    source, target = relation.ends[::-1] if turned else relation.ends
    marks = (bool(relation.first_marks), bool(relation.second_marks))
    course = square_course(relation.path)
    label = text_extent(relation.words)
    return {
        "index": index,
        "key": drawn_as.key if drawn_as is not None else None,
        "source": source,
        "target": target,
        "decorated": [marks[1], marks[0]] if turned else [marks[0], marks[1]],
        "course": [_point(point) for point in (course[::-1] if turned else course)],
        "label": relation.label,
        "label_size": [label.width, label.height] if label is not None else None,
    }


def geometry_of(picture: RenderedPicture, diagram: LaidOutDiagram) -> Wire:
    """*picture* as the lab draws it: every shape and line where PlantUML put it, named as a layout names it."""
    keys = box_keys_by_alias(picture, diagram)
    drawn_as = relation_keys_by_index(picture, diagram)
    return {
        "canvas": _extent(picture.canvas),
        "elements": [_element(element, diagram) for element in picture.elements.values()],
        "boxes": [_box(box, diagram, keys) for box in picture.boxes.values()],
        "relations": [
            _relation(index, relation, drawn_as.get(index)) for index, relation in enumerate(picture.relations)
        ],
    }


def diagram_geometry(
    plantuml_svg: str, frontmatter: Mapping[str, object], ontology: DeclaresElementKinds
) -> Wire | NotReadable:
    """The lab's geometry of the diagram *frontmatter* states, from PlantUML's own picture of it."""
    picture = read_rendered_picture(plantuml_svg)
    if isinstance(picture, NotReadable):
        return picture
    return geometry_of(picture, joined_to_its_picture(frontmatter, Layout(), ontology))
