"""Reads the geometry of a diagram out of the SVG PlantUML rendered for it.

PlantUML draws a description diagram — the kind an ArchiMate, C4 or component body lays out through
GraphViz — as one group per shape, in absolute coordinates: `class="entity"` for a shape with nothing
inside it, `class="cluster"` for a box with shapes inside, `class="link"` for a relation, each naming
what it is in `data-qualified-name` or `data-entity-1`/`-2`. This is the one module family that reads
those names; `tests/architecture/test_each_syntax_has_one_reader.py` holds it to that.

**Fail-closed.** That structure is another project's output, not a contract it has promised. So the
reading is whole or it is `NotReadable`, naming what it met: a group of a class not listed here, a
shape without an outline, a relation ending at nothing drawn. A partial reading would be a layout
with elements silently missing from it, harvested and written back.

**What a name is.** A shape's qualified name is its enclosing boxes' names and its own, joined by
dots — and a name may itself contain the joining dot, because a box declared without an alias is
named by its label ("Team / Project A" is qualified as `Team . Project A`). A shape's enclosing box
is therefore the longest *existing* box name that prefixes it, never a split.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from xml.etree.ElementTree import Element, ParseError  # the types only; input is parsed by defusedxml

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.rendered_picture import (
    DrawnBox,
    DrawnElement,
    MeasuredWord,
    NotReadable,
    RenderedPicture,
)
from src.infrastructure.rendering.layout._svg_drawing import (
    OUTLINE_TAGS,
    SVG_NAMESPACE,
    Unreadable,
    measured_words,
    numbers_of,
    outline_extent,
    tag_of,
)
from src.infrastructure.rendering.layout._svg_relations import read_relation

#: The diagram kind PlantUML states on the root for a picture laid out as shapes and links.
_DESCRIPTION_KIND = "DESCRIPTION"

_BOX_CLASS, _ELEMENT_CLASS, _RELATION_CLASS = "cluster", "entity", "link"

#: Groups that draw around the diagram rather than in it. Read past, never into.
_CHROME_CLASSES = frozenset({"title", "header", "footer", "caption", "legend"})

#: Drawing PlantUML leaves directly in the layer, outside any group: the background rectangle.
_LOOSE_DRAWING_TAGS = OUTLINE_TAGS | {"text", "line"}

#: How far a shape may poke out of the box it is declared inside and still be read as inside it.
#: GraphViz places a member within its cluster; this absorbs stroke widths, not placement.
_NESTING_SLACK = 2.0


@dataclass(frozen=True)
class _Shape:
    """A cluster or an entity as found, before its name is told apart from its boxes' names."""

    qualified_name: str
    group_id: str
    is_box: bool
    extent: Extent
    words: tuple[MeasuredWord, ...]


def _canvas(root: Element) -> Extent:
    view_box = (root.get("viewBox") or "").split()
    try:
        left, top, width, height = (float(value) for value in view_box)
    except ValueError:
        raise Unreadable(f"an <svg> whose viewBox is {root.get('viewBox')!r}") from None
    return Extent(left, top, left + width, top + height)


def _drawing_layer(root: Element) -> Element:
    """The one unclassed group PlantUML puts the whole drawing in."""
    layers = [child for child in root if tag_of(child) == "g"]
    if len(layers) != 1 or layers[0].get("class") is not None:
        raise Unreadable(f"an <svg> with {len(layers)} top-level groups where one drawing layer was expected")
    return layers[0]


def _classed_groups(layer: Element) -> Iterator[tuple[str, Element]]:
    """Each group of the drawing with its class. A group of no known class is unreadable."""
    for child in layer:
        tag = tag_of(child)
        if tag in _LOOSE_DRAWING_TAGS:
            continue  # the background
        if tag != "g":
            raise Unreadable(f"a <{tag}> directly in the drawing layer")
        group_class = child.get("class") or ""
        if group_class in _CHROME_CLASSES:
            continue
        if group_class not in (_BOX_CLASS, _ELEMENT_CLASS, _RELATION_CLASS):
            raise Unreadable(f"a group of class {group_class!r}")
        if any(tag_of(inner) == "g" for inner in child.iter() if inner is not child):
            raise Unreadable(f"a {group_class!r} group with a group inside it")
        yield group_class, child


def _shape(group: Element, *, is_box: bool) -> _Shape:
    name, group_id = group.get("data-qualified-name"), group.get("id")
    if not name or not group_id:
        raise Unreadable("a shape with no qualified name or no id")
    drawings = list(group)
    if not drawings or tag_of(drawings[0]) not in OUTLINE_TAGS:
        met = tag_of(drawings[0]) if drawings else "nothing"
        raise Unreadable(f"the shape {name!r}, which opens with {met} where its outline was expected")
    for drawing in drawings:
        if tag_of(drawing) == "image":
            numbers_of(drawing, "x", "y", "width", "height")
        elif tag_of(drawing) not in OUTLINE_TAGS | {"text", "line"}:
            raise Unreadable(f"a <{tag_of(drawing)}> inside the shape {name!r}")
    return _Shape(
        qualified_name=name,
        group_id=group_id,
        is_box=is_box,
        extent=outline_extent(drawings[0]),
        words=measured_words(drawing for drawing in drawings if tag_of(drawing) == "text"),
    )


def _enclosing_box(shape: _Shape, boxes: Mapping[str, _Shape]) -> _Shape | None:
    """The box *shape* is declared directly inside: the longest box name prefixing its own.

    A prefix is a claim, and the drawing has to bear it out: a box labelled `A.B` standing on the
    canvas is prefixed by a box named `A` without being in it. Where the box a name points at is not
    drawn around the shape, the name can no longer be told apart from its boxes' names, and that is
    unreadable rather than a guess at which.
    """
    named = max(
        (box for name, box in boxes.items() if shape.qualified_name.startswith(name + ".")),
        key=lambda box: len(box.qualified_name),
        default=None,
    )
    if named is not None and not named.extent.encloses(shape.extent, slack=_NESTING_SLACK):
        raise Unreadable(
            f"the shape {shape.qualified_name!r}, named as inside {named.qualified_name!r} "
            "and not drawn inside it"
        )
    return named


def _another_kind(root: Element) -> str | None:
    """What *root* is, where it is not a description diagram PlantUML drew; None where it is one."""
    if root.tag != "{" + SVG_NAMESPACE + "}svg":
        return f"a document whose root is {root.tag!r}"
    kind = root.get("data-diagram-type")
    if kind is None:
        return "an <svg> that does not state which kind of diagram PlantUML drew"
    return None if kind == _DESCRIPTION_KIND else f"a picture of PlantUML's {kind} kind"


def _picture(root: Element) -> RenderedPicture:
    groups = list(_classed_groups(_drawing_layer(root)))
    shapes = [
        _shape(group, is_box=group_class == _BOX_CLASS)
        for group_class, group in groups
        if group_class != _RELATION_CLASS
    ]
    boxes_by_name = {shape.qualified_name: shape for shape in shapes if shape.is_box}

    alias_by_group_id: dict[str, str] = {}
    elements: dict[str, DrawnElement] = {}
    boxes: dict[str, DrawnBox] = {}
    alias_by_name: dict[str, str] = {}
    outer_by_name: dict[str, _Shape | None] = {}
    for shape in shapes:
        outer = _enclosing_box(shape, boxes_by_name)
        alias = shape.qualified_name[len(outer.qualified_name) + 1 :] if outer else shape.qualified_name
        if alias in alias_by_name.values():
            raise Unreadable(f"two shapes drawn under the one name {alias!r}")
        alias_by_group_id[shape.group_id] = alias
        alias_by_name[shape.qualified_name] = alias
        outer_by_name[shape.qualified_name] = outer
    for shape in shapes:
        alias = alias_by_name[shape.qualified_name]
        outer = outer_by_name[shape.qualified_name]
        inside = alias_by_name[outer.qualified_name] if outer else None
        if shape.is_box:
            boxes[alias] = DrawnBox(alias=alias, extent=shape.extent, inside=inside, words=shape.words)
        else:
            elements[alias] = DrawnElement(alias=alias, extent=shape.extent, inside=inside, words=shape.words)

    extent_by_alias = {alias: drawn.extent for alias, drawn in (*elements.items(), *boxes.items())}
    return RenderedPicture(
        canvas=_canvas(root),
        elements=elements,
        boxes=boxes,
        relations=tuple(
            read_relation(group, alias_by_group_id=alias_by_group_id, extent_by_alias=extent_by_alias)
            for group_class, group in groups
            if group_class == _RELATION_CLASS
        ),
    )


def read_rendered_picture(svg: str) -> RenderedPicture | NotReadable:
    """What the picture in *svg* draws, or `NotReadable` naming what it met.

    Never a partial reading, and never an exception for anything about the document: input that is
    not XML, that declares a DTD or an entity, or that is not a description diagram PlantUML drew is
    a `NotReadable` like any other.
    """
    try:
        root = SafeET.fromstring(svg.encode("utf-8"), forbid_dtd=True)
    except (ParseError, DefusedXmlException, ValueError) as exc:
        return NotReadable(met=f"a document that does not parse as safe XML ({type(exc).__name__})")
    if (another := _another_kind(root)) is not None:
        return NotReadable(met=another)
    try:
        return _picture(root)
    except Unreadable as unreadable:
        return NotReadable(met=unreadable.met, stated_the_kind_read=True)
