"""What the layout lab draws with: PlantUML's own drawing of each shape and line, as plain values.

The lab draws the picture the composer draws, so it is given the same markup the composer places —
every outline, fill, stroke, glyph and word as PlantUML drew it — instead of a palette of its own. A
shape is carried by a shift, which the browser applies; a resized shape is drawn again by the
composer's own `fitted_box` and `resized_element` (`reshaped`), so a lab never sets a label or
stretches an outline its own way. A line is the router's, drawn with PlantUML's stroke, and its
decorations are carried from the frame they were drawn in (`frame_as_drawn`) to the line's new end.

A drawing travels as a tree of nodes — tag, attributes, text, children — and only the elements a
rendered shape or line may hold are let through, in either direction: what reaches a browser is SVG
geometry and text, never markup it would parse.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from xml.etree.ElementTree import Element

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.rendered_picture import DrawnRelation, RenderedPicture
from src.infrastructure.rendering.layout._svg_drawing import OUTLINE_TAGS, SVG_NAMESPACE, Unreadable, tag_of
from src.infrastructure.rendering.layout._svg_relations import RelationMarkup
from src.infrastructure.rendering.layout.arrangement import label_extent
from src.infrastructure.rendering.layout.relation_decorations import EndFrame, frame_as_drawn
from src.infrastructure.rendering.layout.shape_drawing import fitted_box, resized_element

type Node = dict[str, object]

_XLINK = "{http://www.w3.org/1999/xlink}"

#: What a rendered shape or line is drawn with; anything else is refused rather than passed on.
DRAWING_TAGS = OUTLINE_TAGS | {"g", "text", "line", "image", "polyline"}


def _attribute_name(name: str) -> str:
    return "xlink:" + name.removeprefix(_XLINK) if name.startswith(_XLINK) else name


def _drawn_tag(element: Element) -> str:
    tag = tag_of(element)
    if tag not in DRAWING_TAGS:
        raise Unreadable(f"a <{tag}> in a drawing the lab is given")
    return tag


def node_of(element: Element) -> Node:
    """*element* and everything in it as a node tree. Raises `Unreadable` for anything not a drawing."""
    return {
        "tag": _drawn_tag(element),
        "attributes": {_attribute_name(name): value for name, value in element.attrib.items()},
        "text": element.text if element.text and element.text.strip(" \t\n") else None,
        "children": [node_of(child) for child in element],
    }


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise Unreadable(f"{value!r} where a string was expected in a drawing")
    return value


def element_of(node: object) -> Element:
    """The markup a node tree states. Raises `Unreadable` for a node that is not a drawing."""
    if not isinstance(node, Mapping):
        raise Unreadable("a drawing that is not a node")
    tag = _text(node.get("tag"))
    if tag not in DRAWING_TAGS:
        raise Unreadable(f"a <{tag}> in a drawing sent to the lab")
    attributes: object = node.get("attributes") or {}
    children: object = node.get("children") or []
    if not isinstance(attributes, Mapping) or not isinstance(children, list):
        raise Unreadable("a drawing node whose attributes or children are malformed")
    element = Element(
        f"{{{SVG_NAMESPACE}}}{tag}",
        {
            (_XLINK + name.removeprefix("xlink:") if name.startswith("xlink:") else name): _text(value)
            for name, value in ((_text(name), value) for name, value in attributes.items())
        },
    )
    text = node.get("text")
    element.text = None if text is None else _text(text)
    element.extend(element_of(child) for child in children)
    return element


def _point(point: Point) -> list[float]:
    return [point.x, point.y]


def _end(marks: Sequence[Element], frame: EndFrame) -> Node:
    return {
        "marks": [node_of(mark) for mark in marks],
        "at": _point(frame.at),
        "heading": [frame.heading[0], frame.heading[1]],
        "gap": frame.gap,
    }


def relation_drawing(
    markup: RelationMarkup, drawn: DrawnRelation, picture: RenderedPicture, *, turned: bool
) -> Node:
    """How one line is drawn: PlantUML's stroke, its decorations in the frames they were drawn in, its label.

    The ends come in the order the lab's course runs — from the relation's source — so *turned* says
    whether that is the reverse of the order the picture files them in.
    """
    first_end, second_end = picture.extent_of(drawn.ends[0]), picture.extent_of(drawn.ends[1])
    if first_end is None or second_end is None:
        raise Unreadable(f"a relation between {drawn.ends[0]!r} and {drawn.ends[1]!r}, one of which is not drawn")
    ends = [
        _end(markup.first_marks, frame_as_drawn(drawn.first_marks, drawn.course[::-1], first_end)),
        _end(markup.second_marks, frame_as_drawn(drawn.second_marks, drawn.course, second_end)),
    ]
    label = label_extent(drawn.words)
    return {
        # As PlantUML drew it, for as long as the line is PlantUML's own.
        "group": node_of(markup.group),
        "line": node_of(markup.line),
        "ends": ends[::-1] if turned else ends,
        "label": None if label is None else {
            "texts": [node_of(text) for text in markup.texts],
            "centre": _point(label.centre),
        },
    }


def _extent_of(wire: object) -> Extent:
    if not isinstance(wire, Mapping):
        raise Unreadable("an extent that is not one")
    try:
        return Extent(*(float(wire[side]) for side in ("left", "top", "right", "bottom")))
    except (KeyError, TypeError, ValueError):
        raise Unreadable("an extent without four numeric sides") from None


def reshaped(shape: Mapping[str, object]) -> Node:
    """A shape's drawing at a new size, drawn by the composer: a box fitted, an element resized."""
    group = element_of(shape.get("drawing"))
    drawn, to = _extent_of(shape.get("drawn")), _extent_of(shape.get("to"))
    return node_of(fitted_box(group, drawn, to) if shape.get("box") is True else resized_element(group, drawn, to))
