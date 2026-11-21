"""Draws a laid-out diagram: PlantUML's picture of it, composed again from the layout it states.

PlantUML stays the notation. It is asked for its picture of the diagram once; the composer reads that
picture (`plantuml_svg_reader`), decides where everything goes under the layout (`arrangement`) and
writes a picture of the same structure with each part in its place: elements re-placed or resized,
boxes fitted round their contents, relations drawn along their courses, the title and legend carried
with the diagram, the canvas grown or shrunk to what is drawn.

**The composed picture is a picture like any other.** It keeps the structure and every identifying
attribute of the one it was composed from, in absolute coordinates, so it reads back through the same
reader as what it shows: the viewer's element map, the rendered-picture checks and a later harvest
all work on it unchanged.

**Fail-closed.** A picture this project cannot read, one holding a drawing it cannot place again, or
one whose layout leaves a relation no route that keeps the hard rules, is not composed in part:
`compose` answers `NotComposed` saying what it met, and the caller keeps PlantUML's own picture — a
diagram drawn as before rather than one drawn wrongly.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.rendered_picture import NotReadable
from src.infrastructure.rendering.layout._svg_drawing import SVG_NAMESPACE, Unreadable
from src.infrastructure.rendering.layout.arrangement import KEEP_UNMOVED_LINES, Arrangement, arrange, label_extent
from src.infrastructure.rendering.layout.plantuml_svg_reader import RenderedDrawing, read_rendered_drawing
from src.infrastructure.rendering.layout.relation_drawing import drawn_relation
from src.infrastructure.rendering.layout.shape_drawing import fitted_box, placed_shape, resized_element
from src.infrastructure.rendering.layout.svg_markup import Motion, drawn_extent, fitted, moved
from src.infrastructure.rendering.layout.svg_path_data import written_number

_XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"


@dataclass(frozen=True)
class NotComposed:
    """A picture that was not composed from its layout, and what stood in the way."""

    met: str
    #: The relations the layout leaves no route for, where that is why; by what their ends are called.
    relations_unroutable: tuple[str, ...] = ()


def _around(extents: list[Extent]) -> Extent:
    return Extent(
        min(extent.left for extent in extents), min(extent.top for extent in extents),
        max(extent.right for extent in extents), max(extent.bottom for extent in extents),
    )


def _diagram_extent_drawn(drawing: RenderedDrawing) -> Extent:
    """What PlantUML's shapes and relations occupied, title and legend aside."""
    picture = drawing.picture
    occupied = [shape.extent for shape in (*picture.elements.values(), *picture.boxes.values())]
    occupied += [around for relation in picture.relations if (around := Extent.around(relation.course)) is not None]
    occupied += [label for relation in picture.relations if (label := label_extent(relation.words)) is not None]
    return _around(occupied) if occupied else picture.canvas


def _diagram_extent_now(drawing: RenderedDrawing, arrangement: Arrangement) -> Extent:
    occupied = [*arrangement.elements.values(), *arrangement.boxes.values()]
    for relation, drawn in zip(arrangement.relations, drawing.picture.relations, strict=True):
        if (around := Extent.around(relation.course)) is not None:
            occupied.append(around)
        label = label_extent(drawn.words)
        if label is not None and relation.label_centre is not None:
            half_width, half_height = label.width / 2, label.height / 2
            occupied.append(Extent(
                relation.label_centre.x - half_width, relation.label_centre.y - half_height,
                relation.label_centre.x + half_width, relation.label_centre.y + half_height,
            ))
    return _around(occupied) if occupied else drawing.picture.canvas


def _carried_with(part: Extent, was: Extent, now: Extent) -> Motion:
    """How something drawn around the diagram moves with it: it keeps to the side or the middle it was at."""
    if part.centre.x < was.left:
        dx = now.left - was.left
    elif part.centre.x > was.right:
        dx = now.right - was.right
    else:
        dx = now.centre.x - was.centre.x
    dy = now.bottom - was.bottom if part.centre.y > was.bottom else now.top - was.top
    return Motion.shift(dx, dy)


def _shape(drawing: RenderedDrawing, arrangement: Arrangement, alias: str) -> Element:
    group, picture = drawing.shapes[alias], drawing.picture
    if alias in picture.boxes:
        return fitted_box(group, picture.boxes[alias].extent, arrangement.boxes[alias])
    drawn, to = picture.elements[alias].extent, arrangement.elements[alias]
    return resized_element(group, drawn, to) if alias in arrangement.resized else placed_shape(group, drawn, to)


def _sized(root: Element, canvas: Extent) -> Element:
    """A root like *root*, stating *canvas* as its size wherever a root states one."""
    sized = Element(root.tag, dict(root.attrib))
    width, height = written_number(canvas.width), written_number(canvas.height)
    sized.set("width", f"{width}px")
    sized.set("height", f"{height}px")
    sized.set("viewBox", f"{written_number(canvas.left)} {written_number(canvas.top)} {width} {height}")
    kept = [
        rule for rule in (root.get("style") or "").split(";")
        if rule.strip() and rule.split(":")[0].strip() not in ("width", "height")
    ]
    sized.set("style", ";".join([f"width:{width}px", f"height:{height}px", *kept]) + ";")
    return sized


class _NoRoute(Exception):
    def __init__(self, relations: tuple[str, ...]) -> None:
        super().__init__(relations)
        self.relations = relations


def _composed(drawing: RenderedDrawing, diagram: LaidOutDiagram, keep_unmoved_lines: bool) -> Element:
    picture = drawing.picture
    arrangement = arrange(picture, diagram, keep_unmoved_lines=keep_unmoved_lines)
    if arrangement.unroutable:
        raise _NoRoute(arrangement.unroutable)
    was, now = _diagram_extent_drawn(drawing), _diagram_extent_now(drawing, arrangement)

    chrome = [
        moved(part, _carried_with(extent, was, now)) if (extent := drawn_extent(part)) is not None
        else copy.deepcopy(part)
        for part in drawing.chrome
    ]
    drawn_over = [was, *(extent for part in drawing.chrome if (extent := drawn_extent(part)) is not None)]
    drawn_now = [now, *(extent for part in chrome if (extent := drawn_extent(part)) is not None)]
    everything_was, everything_now = _around(drawn_over), _around(drawn_now)
    # The margin PlantUML left on each side of what it drew is kept on each side of what is drawn now.
    canvas = Extent(
        everything_now.left - (everything_was.left - picture.canvas.left),
        everything_now.top - (everything_was.top - picture.canvas.top),
        everything_now.right + (picture.canvas.right - everything_was.right),
        everything_now.bottom + (picture.canvas.bottom - everything_was.bottom),
    )

    root = _sized(drawing.root, canvas)
    layer = Element(f"{{{SVG_NAMESPACE}}}g")
    for child in drawing.root:
        if child.tag != layer.tag:
            root.append(copy.deepcopy(child))
    root.append(layer)
    layer.extend(fitted(part, picture.canvas, canvas) for part in drawing.backdrop)
    layer.extend(chrome)
    layer.extend(_shape(drawing, arrangement, alias) for alias in arrangement.paint_order)
    for markup, drawn, arranged in zip(drawing.relations, picture.relations, arrangement.relations, strict=True):
        ends = (picture.extent_of(drawn.ends[0]), picture.extent_of(drawn.ends[1]))
        if ends[0] is None or ends[1] is None:
            raise Unreadable(f"a relation between {drawn.ends[0]!r} and {drawn.ends[1]!r}, one of which is not drawn")
        layer.append(drawn_relation(markup, drawn, arranged, (ends[0], ends[1])))
    return root


def compose(
    plantuml_svg: str, diagram: LaidOutDiagram, *, keep_unmoved_lines: bool = KEEP_UNMOVED_LINES,
) -> str | NotComposed:
    """The picture in *plantuml_svg* drawn again from *diagram*'s layout, or `NotComposed` saying why not."""
    drawing = read_rendered_drawing(plantuml_svg)
    if isinstance(drawing, NotReadable):
        return NotComposed(drawing.met)
    try:
        root = _composed(drawing, diagram, keep_unmoved_lines)
    except Unreadable as unreadable:
        return NotComposed(unreadable.met)
    except _NoRoute as no_route:
        return NotComposed(
            "no route keeps every rule for the relation between " + "; between ".join(no_route.relations),
            relations_unroutable=no_route.relations,
        )
    ElementTree.register_namespace("", SVG_NAMESPACE)
    ElementTree.register_namespace("xlink", _XLINK_NAMESPACE)
    return ElementTree.tostring(root, encoding="unicode")
