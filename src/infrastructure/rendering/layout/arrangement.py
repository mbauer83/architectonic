"""Where everything on a laid-out diagram's picture goes: a picture and a layout in, geometry out.

No markup here. The composer draws what this decides, and what this decides is stated in the
picture's own terms — aliases, extents, courses — so it can be checked without rendering anything:

* an **element** sits where the layout places it, at the size it states or else the size the renderer
  drew it; one the layout does not place stays where the renderer put it;
* a **box** — a grouping of either kind, or an element holding its parts — is what its contents need
  with the renderer's own padding and never narrower than its title, widened to what the layout
  states for it and never narrowed;
* a **relation** runs the course its stated route completes to; every other one is routed by
  `routing`, which keeps the hard readability rules, and one no route reaches is named, never drawn
  through something;
* a **label** sits where its route's anchor says, or beside its route clear of every element, every
  text and every line;
* **painting** follows containment: a box and everything in it are one unit, siblings in `z` order
  with ties in the order the renderer drew them, boxes before the elements beside them.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Placed, Route
from src.domain.diagrams.layout.layout_checks import placed_extent
from src.domain.diagrams.layout.orthogonal import course_of
from src.domain.diagrams.layout.rendered_picture import DrawnBox, MeasuredWord, RenderedPicture, extent_across
from src.domain.diagrams.layout.routing.router import route_all
from src.domain.diagrams.layout.routing.scene import Connector, RoutingScene
from src.domain.diagrams.layout.text_clearance import padded, text_extent, title_band
from src.infrastructure.rendering.layout.box_identities import box_keys_by_alias
from src.infrastructure.rendering.layout.label_placement import label_box, placed_label
from src.infrastructure.rendering.layout.relation_identities import relation_keys_by_index

#: How far a size may differ from the one the renderer drew and still be the same size.
_SAME_SIZE = 0.5

#: The least room kept either side of a box's title.
_TITLE_MARGIN = 8.0


@dataclass(frozen=True)
class ArrangedRelation:
    """One relation of the picture as it is to be drawn."""

    #: From the picture's first end to its second, the order its marks are filed in.
    course: tuple[Point, ...]
    #: Where the middle of its label goes, or None for a relation that carries none.
    label_centre: Point | None = None


@dataclass(frozen=True)
class Arrangement:
    """Everything a laid-out picture draws, each where it goes, by the alias the picture knows it by."""

    elements: Mapping[str, Extent]
    #: The elements drawn at a stated size that is not the size the renderer drew them.
    resized: frozenset[str]
    boxes: Mapping[str, Extent]
    #: In the order of the picture's relations; none at all where one is unroutable, since nothing is drawn.
    relations: tuple[ArrangedRelation, ...]
    #: Every box and element, back to front.
    paint_order: tuple[str, ...]
    #: The relations no route reaches that keeps every hard rule, by what their ends are called.
    unroutable: tuple[str, ...] = ()


def label_extent(words: Sequence[MeasuredWord]) -> Extent | None:
    """The rectangle a run of label text occupies, or None for no text."""
    return text_extent(words)


def _union(extents: Sequence[Extent]) -> Extent:
    return Extent(
        min(extent.left for extent in extents), min(extent.top for extent in extents),
        max(extent.right for extent in extents), max(extent.bottom for extent in extents),
    )


def _stated_reach(stated: Placed | None) -> Extent | None:
    """What a box's statement reaches: its corner, and its far corner where it is sized."""
    if stated is None:
        return None
    return placed_extent(stated) or Extent(stated.x, stated.y, stated.x, stated.y)


def _wide_enough_for_its_title(needed: Extent, box: DrawnBox) -> Extent:
    """*needed* widened about its middle until the box's title fits with the margin PlantUML gave it."""
    across = extent_across(box.words)
    if across is None:
        return needed
    title, drawn = across[1] - across[0], box.extent
    least = title + 2 * max(_TITLE_MARGIN, min(across[0] - drawn.left, drawn.right - across[1]))
    if needed.width >= least:
        return needed
    grow = (least - needed.width) / 2
    return Extent(needed.left - grow, needed.top, needed.right + grow, needed.bottom)


def fitted_boxes(
    picture: RenderedPicture, elements: Mapping[str, Extent], stated: Callable[[str], Extent | None],
) -> dict[str, Extent]:
    """Every box of *picture* where it is drawn now: the box rule, which the canvas keeps too.

    A box is what its contents need — the elements where *elements* has them now, the boxes inside it
    fitted the same way — with the padding the renderer gave it, never narrower than its title, and
    grown to take in what *stated* reaches for it; never narrowed. `tests/fixtures/layout_geometry/
    boxes.json` holds the canvas's `fittedBoxes` to the same answers.
    """
    children: dict[str | None, list[str]] = defaultdict(list)
    for shape in (*picture.boxes.values(), *picture.elements.values()):
        children[shape.inside].append(shape.alias)
    boxes: dict[str, Extent] = {}

    def now(alias: str) -> Extent:
        return elements[alias] if alias in elements else fit(alias)

    def fit(alias: str) -> Extent:
        if alias in boxes:
            return boxes[alias]
        box, inside = picture.boxes[alias], children.get(alias, [])
        drawn = needed = box.extent
        if inside:
            before = _union([extent for child in inside if (extent := picture.extent_of(child)) is not None])
            after = _union([now(child) for child in inside])
            needed = Extent(
                after.left - (before.left - drawn.left), after.top - (before.top - drawn.top),
                after.right + (drawn.right - before.right), after.bottom + (drawn.bottom - before.bottom),
            )
        needed = _wide_enough_for_its_title(needed, box)
        reach = stated(alias)
        boxes[alias] = needed if reach is None else _union([needed, reach])
        return boxes[alias]

    for alias in picture.boxes:
        fit(alias)
    return boxes


@dataclass(frozen=True)
class RoutingInput:
    """What a picture's arrangement asks of the router, and what it keeps to draw the answer."""

    scene: RoutingScene
    connectors: tuple[Connector, ...]
    #: The courses the layout states whole, by the index of the picture's relation.
    stated: Mapping[int, tuple[Point, ...]]
    routes: Mapping[int, Route]
    keyed: Mapping[int, tuple[str, bool]]


class _Arranging:
    """One picture being arranged by one layout: the joins made once, the answers built on each other."""

    def __init__(self, picture: RenderedPicture, diagram: LaidOutDiagram) -> None:
        self._picture, self._diagram, self._layout = picture, diagram, diagram.layout
        self._box_keys = box_keys_by_alias(picture, diagram)
        self._children: dict[str | None, list[str]] = defaultdict(list)
        for shape in (*picture.boxes.values(), *picture.elements.values()):
            self._children[shape.inside].append(shape.alias)
        self.resized: set[str] = set()
        self.elements = {alias: self._element_extent(alias) for alias in picture.elements}
        self.boxes = fitted_boxes(picture, self.elements, lambda alias: _stated_reach(self._stated_for(alias)))

    def _stated_for(self, alias: str) -> Placed | None:
        """What the layout states for a shape: an element by its instance, a box by its key."""
        instance = self._diagram.instance_by_alias.get(alias)
        if instance is not None:
            return self._layout.elements.get(instance)
        return self._layout.boxes.get(self._box_keys.get(alias, ""))

    def _element_extent(self, alias: str) -> Extent:
        drawn, stated = self._picture.elements[alias].extent, self._stated_for(alias)
        placed = placed_extent(stated, drawn_size=(drawn.width, drawn.height)) if stated is not None else None
        if placed is None:
            return drawn
        if abs(placed.width - drawn.width) > _SAME_SIZE or abs(placed.height - drawn.height) > _SAME_SIZE:
            self.resized.add(alias)
        return placed

    def _stacking(self, alias: str) -> int:
        instance = self._diagram.instance_by_alias.get(alias)
        return self._layout.z.get(instance if instance is not None else self._box_keys.get(alias, ""), 0)

    def paint_order(self, parent: str | None = None) -> list[str]:
        """A box, then everything in it, as one unit; siblings by `z`, ties as the renderer drew them."""
        siblings = self._children.get(parent, [])
        ordered = sorted(siblings, key=lambda alias: (self._stacking(alias), siblings.index(alias)))
        return [painted for alias in ordered for painted in (alias, *self.paint_order(alias))]

    def _keyed(self) -> dict[int, tuple[str, bool]]:
        """Which stated relation each relation of the picture is, and whether it is drawn target-first."""
        return {
            index: (drawn.key, drawn.turned)
            for index, drawn in relation_keys_by_index(self._picture, self._diagram).items()
        }

    def bands(self) -> dict[str, Extent]:
        """Each box's title band where it is drawn now: the band it had, carried as its title is — with
        the box's top and its middle (`shape_drawing.fitted_box`). As wide as the title, not the box: a
        band the box's whole width would leave a line from outside no way in but round the side."""
        bands: dict[str, Extent] = {}
        for alias, box in self._picture.boxes.items():
            title = text_extent(box.words)
            if title is not None:
                drawn, now = box.extent, self.boxes[alias]
                dx, dy = now.centre.x - drawn.centre.x, now.top - drawn.top
                carried = Extent(title.left + dx, title.top + dy, title.right + dx, title.bottom + dy)
                bands[alias] = title_band(now, carried)
        return bands

    def _labels_outside(self) -> dict[str, Extent]:
        """Each element's label set outside its outline — an actor's, below it — where it is now."""
        labels: dict[str, Extent] = {}
        for alias, element in self._picture.elements.items():
            label = text_extent(element.words)
            if label is None or element.extent.encloses(label) or alias in self.resized:
                continue
            dx, dy = self.elements[alias].left - element.extent.left, self.elements[alias].top - element.extent.top
            moved = padded(label)
            labels[alias] = Extent(moved.left + dx, moved.top + dy, moved.right + dx, moved.bottom + dy)
        return labels

    def text(self) -> dict[str, Extent]:
        """Every text region a route keeps out of, before any relation's label is placed."""
        return {
            **{f"band:{alias}": band for alias, band in self.bands().items()},
            **{f"label:{alias}": label for alias, label in self._labels_outside().items()},
        }

    def routing(self) -> RoutingInput:
        """What the router is asked: the scene as arranged, and every relation no stated route decides.

        A relation whose layout states its bends between two stated ports runs that course, and is a fixed
        line to the others. One that states only its ports is routed between them: its bends are unstated,
        so they are the router's, and the route goes round whatever lies between (a straightened line).
        """
        extents: dict[str, Extent] = {**self.boxes, **self.elements}
        keyed = self._keyed()
        courses: dict[int, tuple[Point, ...]] = {}
        routes: dict[int, Route] = {}
        connectors: list[Connector] = []
        for index, relation in enumerate(self._picture.relations):
            key, turned = keyed.get(index, ("", False))
            source, target = relation.ends[::-1] if turned else relation.ends
            routes[index] = self._layout.relations.get(key, Route())
            stated = course_of(routes[index], extents[source], extents[target]) if routes[index].via else None
            if stated is not None:
                courses[index] = stated[::-1] if turned else stated
            else:
                marks = (bool(relation.first_marks), bool(relation.second_marks))
                connectors.append(Connector(
                    str(index), source, target, (marks[1], marks[0]) if turned else marks,
                    routes[index].source, routes[index].target,
                ))
        scene = RoutingScene(
            elements=self.elements, boxes=self.boxes, text=self.text(), fixed_lines=list(courses.values()),
        )
        return RoutingInput(scene, tuple(connectors), courses, routes, keyed)

    def relations(self) -> tuple[tuple[ArrangedRelation, ...], tuple[str, ...]]:
        """Every relation's course and label, and the relations no route reaches.

        Every relation the layout states no whole route for is routed (`routing`), all of them
        together, and nudged apart.
        """
        asked = self.routing()
        courses = dict(asked.stated)
        result = route_all(asked.scene, asked.connectors)
        for key, routed in result.routes.items():
            index = int(key)
            courses[index] = routed.course[::-1] if asked.keyed.get(index, ("", False))[1] else routed.course
        unroutable = tuple(
            " and ".join(self._picture.label_of(end) or end for end in self._picture.relations[int(key)].ends)
            for key in result.unroutable
        )
        if unroutable:
            # A relation no route reaches has no course to label, and the picture is not drawn at all.
            return (), unroutable
        return self._labelled(courses, asked.routes, asked.keyed), unroutable

    def _labelled(
        self, courses: Mapping[int, tuple[Point, ...]], routes: Mapping[int, Route],
        keyed: Mapping[int, tuple[str, bool]],
    ) -> tuple[ArrangedRelation, ...]:
        taken = [*self.elements.values(), *self.text().values()]
        lines = list(courses.values())
        arranged: list[ArrangedRelation] = []
        for index, relation in enumerate(self._picture.relations):
            course, text = courses[index], label_extent(relation.words)
            if text is None:
                arranged.append(ArrangedRelation(course))
                continue
            size = (text.width, text.height)
            # An anchor is stated along the route from its source; the course here may run the other way.
            as_stated = course[::-1] if keyed.get(index, ("", False))[1] else course
            anchor = routes[index].label or placed_label(as_stated, size, taken, lines)
            box = label_box(as_stated, anchor, size)
            taken.append(box)
            arranged.append(ArrangedRelation(course, box.centre))
        return tuple(arranged)


def routing_input(picture: RenderedPicture, diagram: LaidOutDiagram) -> RoutingInput:
    """What the router is asked once *diagram*'s layout places *picture*'s shapes."""
    return _Arranging(picture, diagram).routing()


def arrange(picture: RenderedPicture, diagram: LaidOutDiagram) -> Arrangement:
    """Where everything *picture* draws goes once *diagram*'s layout is applied to it."""
    arranged = _Arranging(picture, diagram)
    relations, unroutable = arranged.relations()
    return Arrangement(
        elements=arranged.elements,
        resized=frozenset(arranged.resized),
        boxes=arranged.boxes,
        relations=relations,
        paint_order=tuple(arranged.paint_order()),
        unroutable=unroutable,
    )
