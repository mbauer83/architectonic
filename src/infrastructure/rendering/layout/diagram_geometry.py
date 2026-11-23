"""What the layout lab is given to draw a diagram from: PlantUML's picture of it, read, with its joins made.

Nothing is read here that the product does not already read. The picture comes through the one reader
of PlantUML's structure (`plantuml_svg_reader`); which instance, grouping and stated relation each
shape and line is comes through the joins the composer makes (`diagram_layout_statement`,
`box_identities`, `relation_identities`); a box's title band and an element's outside label are the
text regions the router keeps out of (`text_clearance`); what each is drawn with is PlantUML's own
markup of it (`drawing`). This module only writes those answers down as plain values a browser can
take, so the lab draws exactly what the composer would arrange, as the composer would draw it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.application.modeling.diagram_layout_statement import DeclaresElementKinds, joined_to_its_picture
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import LAYOUT_KEY, Layout, layout_as_written, read_layout
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
from src.infrastructure.rendering.layout._svg_drawing import Unreadable
from src.infrastructure.rendering.layout._svg_relations import RelationMarkup
from src.infrastructure.rendering.layout.box_identities import box_keys_by_alias
from src.infrastructure.rendering.layout.diagram_picture import NotDrawn, measure_composition, plantuml_svg
from src.infrastructure.rendering.layout.drawing_wire import node_of, relation_drawing
from src.infrastructure.rendering.layout.membership_placement import with_new_members
from src.infrastructure.rendering.layout.plantuml_svg_reader import RenderedDrawing, read_rendered_drawing
from src.infrastructure.rendering.layout.relation_identities import DrawnAs, relation_keys_by_index
from src.infrastructure.write.artifact_write.parse_existing import ParsedDiagram

type Wire = dict[str, object]


def _extent(extent: Extent | None) -> Wire | None:
    if extent is None:
        return None
    return {"left": extent.left, "top": extent.top, "right": extent.right, "bottom": extent.bottom}


def _words(words: Sequence[MeasuredWord]) -> list[Wire]:
    return [{"text": word.text, "x": word.start.x, "y": word.start.y, "width": word.width} for word in words]


def _point(point: Point) -> list[float]:
    return [point.x, point.y]


def _element(element: DrawnElement, diagram: LaidOutDiagram, drawing: RenderedDrawing) -> Wire:
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
        "drawing": node_of(drawing.shapes[element.alias]),
    }


def _box(box: DrawnBox, diagram: LaidOutDiagram, keys: Mapping[str, str], drawing: RenderedDrawing) -> Wire:
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
        "drawing": node_of(drawing.shapes[box.alias]),
    }


def _relation(
    index: int, relation: DrawnRelation, drawn_as: DrawnAs | None, markup: RelationMarkup, picture: RenderedPicture
) -> Wire:
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
        "drawing": relation_drawing(markup, relation, picture, turned=turned),
    }


def geometry_of(drawing: RenderedDrawing, diagram: LaidOutDiagram) -> Wire:
    """A picture as the lab draws it: every shape and line where PlantUML put it, named as a layout names it,
    with PlantUML's own drawing of each — and of the backdrop behind them — to draw it with."""
    picture = drawing.picture
    keys = box_keys_by_alias(picture, diagram)
    drawn_as = relation_keys_by_index(picture, diagram)
    return {
        "canvas": _extent(picture.canvas),
        "backdrop": [node_of(part) for part in drawing.backdrop],
        "elements": [_element(element, diagram, drawing) for element in picture.elements.values()],
        "boxes": [_box(box, diagram, keys, drawing) for box in picture.boxes.values()],
        "relations": [
            _relation(index, relation, drawn_as.get(index), markup, picture)
            for index, (relation, markup) in enumerate(zip(picture.relations, drawing.relations, strict=True))
        ],
    }


def diagram_geometry(
    plantuml_svg: str, frontmatter: Mapping[str, object], ontology: DeclaresElementKinds,
    *, arrangement: dict[str, Any] | None = None, previous: frozenset[str] = frozenset(),
) -> Wire | NotReadable:
    """The lab's geometry of the diagram *frontmatter* states, from PlantUML's own picture of it."""
    drawing = read_rendered_drawing(plantuml_svg)
    if isinstance(drawing, NotReadable):
        return drawing
    try:
        layout = read_layout(arrangement) if arrangement else Layout()
        diagram = joined_to_its_picture(frontmatter, layout, ontology)
        result = geometry_of(drawing, diagram)
        if arrangement:
            new = frozenset(diagram.instance_by_alias.values()) - previous
            result["layout"] = layout_as_written(with_new_members(drawing.picture, diagram, new))
        return result
    except Unreadable as unreadable:
        return NotReadable(met=unreadable.met)


def stored_geometry(
    parsed: ParsedDiagram, artifact_id: str, root: Path, ontology: DeclaresElementKinds,
) -> Wire:
    """The geometry of a stored diagram as it is drawn now."""
    return geometry_response(parsed.puml_body, artifact_id, dict(parsed.frontmatter), root, ontology)


def geometry_response(
    puml: str, artifact_id: str, frontmatter: Mapping[str, object], root: Path, ontology: DeclaresElementKinds,
    *, generated: bool = False, arrangement: dict[str, Any] | None = None, previous: frozenset[str] = frozenset(),
) -> Wire:
    """The geometry of *puml*, stored or composed (*generated*); raises ValueError when it cannot be drawn.

    With an *arrangement*, members not in *previous* are placed and the returned layout replaces the stored one.
    """
    diagram_type = str(frontmatter.get("diagram-type", "archimate"))
    try:
        svg = measure_composition(puml, root, diagram_type)[1] if generated else plantuml_svg(puml, root, diagram_type)
    except NotDrawn as refusal:
        raise ValueError(str(refusal)) from refusal
    geometry = diagram_geometry(svg, frontmatter, ontology, arrangement=arrangement, previous=previous)
    if isinstance(geometry, NotReadable):
        raise ValueError(f"This diagram's picture cannot be arranged: {geometry.met}")
    stored = frontmatter.get(LAYOUT_KEY)
    return {
        "artifact_id": str(frontmatter.get("artifact-id", artifact_id)),
        "name": str(frontmatter.get("name") or artifact_id),
        **({"layout": stored} if isinstance(stored, dict) and stored else {}),
        **geometry,
    }
