"""Where everything on a laid-out diagram's picture goes: a picture and a layout in, geometry out.

No markup here. The composer draws what this decides, and what this decides is stated in the
picture's own terms — aliases, extents, courses — so it can be checked without rendering anything:

* an **element** sits where the layout places it, at the size it states or else the size the renderer
  drew it; one the layout does not place stays where the renderer put it;
* a **box** — a grouping of either kind, or an element holding its parts — is what its contents need
  with the renderer's own padding and never narrower than its title, widened to what the layout
  states for it and never narrowed;
* a **relation** runs the course its stated route completes to; one whose ends did not move keeps
  the renderer's line (`KEEP_UNMOVED_LINES`); every other one is routed by `routing`, which keeps the
  hard readability rules, and one no route reaches is named, never drawn through something;
* a **label** sits where its route's anchor says, or beside its route clear of every element, every
  text and every line;
* **painting** follows containment: a box and everything in it are one unit, siblings in `z` order
  with ties in the order the renderer drew them, boxes before the elements beside them.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Placed, Route
from src.domain.diagrams.layout.layout_checks import placed_extent
from src.domain.diagrams.layout.orthogonal import course_of
from src.domain.diagrams.layout.rendered_picture import DrawnBox, MeasuredWord, RenderedPicture, extent_across
from src.domain.diagrams.layout.route_quality import square_course
from src.domain.diagrams.layout.routing.router import route_all
from src.domain.diagrams.layout.routing.scene import Connector, RoutingScene
from src.domain.diagrams.layout.text_clearance import padded, text_extent, title_band
from src.infrastructure.rendering.layout.box_identities import box_keys_by_alias
from src.infrastructure.rendering.layout.label_placement import label_box, placed_label

#: Whether a relation whose two ends did not move keeps the line the renderer drew, rather than being
#: routed with the rest. The one switch for it: on, a picture changes only where something moved, and
#: the verifier reports any hard rule a kept line breaks; off, every line follows the rules.
KEEP_UNMOVED_LINES: Final = True

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
    #: Drawn exactly as the renderer drew it: nothing about it, its ends or what it passes changed.
    as_drawn: bool = False


@dataclass(frozen=True)
class Arrangement:
    """Everything a laid-out picture draws, each where it goes, by the alias the picture knows it by."""

    elements: Mapping[str, Extent]
    #: The elements drawn at a stated size that is not the size the renderer drew them.
    resized: frozenset[str]
    boxes: Mapping[str, Extent]
    #: In the order of the picture's relations.
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


def _widened_to(needed: Extent, stated: Placed | None) -> Extent:
    """*needed* grown to take in what is stated for the box: its corner, and its far corner where it is sized."""
    if stated is None:
        return needed
    far = placed_extent(stated) or Extent(stated.x, stated.y, stated.x, stated.y)
    return _union([needed, far])


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
        self.boxes: dict[str, Extent] = {}
        for alias in picture.boxes:
            self._box_extent(alias)

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

    def _extent_now(self, alias: str) -> Extent:
        return self.elements[alias] if alias in self.elements else self._box_extent(alias)

    def _box_extent(self, alias: str) -> Extent:
        if alias in self.boxes:
            return self.boxes[alias]
        drawn, inside = self._picture.boxes[alias].extent, self._children.get(alias, [])
        needed = drawn
        if inside:
            before = _union([extent for child in inside if (extent := self._picture.extent_of(child)) is not None])
            now = _union([self._extent_now(child) for child in inside])
            needed = Extent(
                now.left - (before.left - drawn.left), now.top - (before.top - drawn.top),
                now.right + (drawn.right - before.right), now.bottom + (drawn.bottom - before.bottom),
            )
        needed = _wide_enough_for_its_title(needed, self._picture.boxes[alias])
        self.boxes[alias] = _widened_to(needed, self._stated_for(alias))
        return self.boxes[alias]

    def _stacking(self, alias: str) -> int:
        instance = self._diagram.instance_by_alias.get(alias)
        return self._layout.z.get(instance if instance is not None else self._box_keys.get(alias, ""), 0)

    def paint_order(self, parent: str | None = None) -> list[str]:
        """A box, then everything in it, as one unit; siblings by `z`, ties as the renderer drew them."""
        siblings = self._children.get(parent, [])
        ordered = sorted(siblings, key=lambda alias: (self._stacking(alias), siblings.index(alias)))
        return [painted for alias in ordered for painted in (alias, *self.paint_order(alias))]

    def _keyed(self) -> dict[int, tuple[str, bool]]:
        """Which stated relation each relation of the picture is, and whether it is drawn target-first.

        Several relations between one pair are matched in order: the picture's and the diagram's.
        """
        waiting: dict[frozenset[str], list[int]] = defaultdict(list)
        for index, relation in enumerate(self._picture.relations):
            waiting[frozenset(relation.ends)].append(index)
        keyed: dict[int, tuple[str, bool]] = {}
        for key, (source, target) in self._diagram.relations.items():
            if between := waiting.get(frozenset((source, target))):
                index = between.pop(0)
                keyed[index] = (key, self._picture.relations[index].ends[0] != source)
        return keyed

    def bands(self) -> dict[str, Extent]:
        """Each box's title band where it is drawn now: the band it had, carried with the box's top."""
        bands: dict[str, Extent] = {}
        for alias, box in self._picture.boxes.items():
            title = text_extent(box.words)
            if title is not None:
                drawn, now = box.extent, self.boxes[alias]
                band = title_band(drawn, title)
                bands[alias] = Extent(now.left, now.top, now.right, now.top + (band.bottom - drawn.top))
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

    def relations(self, keep_unmoved_lines: bool) -> tuple[tuple[ArrangedRelation, ...], tuple[str, ...]]:
        """Every relation's course and label, and the relations no route reaches.

        A relation whose whole route the layout states runs it. With *keep_unmoved_lines*, one whose two
        ends did not move keeps the renderer's line, and what it breaks is the verifier's to report.
        Every other one is routed (`routing`), and all of them together are nudged apart.
        """
        extents: dict[str, Extent] = {**self.boxes, **self.elements}
        keyed = self._keyed()
        courses: dict[int, tuple[Point, ...]] = {}
        routes: dict[int, Route] = {}
        kept: dict[int, tuple[Point, ...]] = {}
        connectors: list[Connector] = []
        for index, relation in enumerate(self._picture.relations):
            key, turned = keyed.get(index, ("", False))
            source, target = relation.ends[::-1] if turned else relation.ends
            routes[index] = self._layout.relations.get(key, Route())
            stated = course_of(routes[index], extents[source], extents[target])
            if keep_unmoved_lines and key not in self._layout.relations and all(map(self._unchanged, relation.ends)):
                kept[index] = relation.course
            elif stated is not None:
                courses[index] = stated[::-1] if turned else stated
            else:
                marks = (bool(relation.first_marks), bool(relation.second_marks))
                connectors.append(Connector(
                    str(index), source, target, (marks[1], marks[0]) if turned else marks,
                    routes[index].source, routes[index].target,
                ))
        scene = RoutingScene(
            elements=self.elements, boxes=self.boxes, text=self.text(),
            fixed_lines=[*courses.values(), *(square_course(self._picture.relations[index].path) for index in kept)],
        )
        result = route_all(scene, connectors)
        for key, routed in result.routes.items():
            index = int(key)
            courses[index] = routed.course[::-1] if keyed.get(index, ("", False))[1] else routed.course
        unroutable = tuple(
            " and ".join(self._picture.label_of(end) or end for end in self._picture.relations[int(key)].ends)
            for key in result.unroutable
        )
        return self._labelled(courses, routes, keyed, kept), unroutable

    def _unchanged(self, alias: str) -> bool:
        drawn = self._picture.extent_of(alias)
        now = self.elements.get(alias) or self.boxes.get(alias)
        return drawn is not None and now is not None and all(
            abs(was - is_now) <= _SAME_SIZE
            for was, is_now in zip(
                (drawn.left, drawn.top, drawn.right, drawn.bottom), (now.left, now.top, now.right, now.bottom),
                strict=True,
            )
        )

    def _labelled(
        self, courses: Mapping[int, tuple[Point, ...]], routes: Mapping[int, Route],
        keyed: Mapping[int, tuple[str, bool]], kept: Mapping[int, tuple[Point, ...]],
    ) -> tuple[ArrangedRelation, ...]:
        kept_labels = [
            label for index in kept if (label := label_extent(self._picture.relations[index].words)) is not None
        ]
        taken = [*self.elements.values(), *self.text().values(), *kept_labels]
        lines = [*courses.values(), *kept.values()]
        arranged: list[ArrangedRelation] = []
        for index, relation in enumerate(self._picture.relations):
            if index in kept:
                label = label_extent(relation.words)
                arranged.append(ArrangedRelation(kept[index], label.centre if label else None, as_drawn=True))
                continue
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


def arrange(
    picture: RenderedPicture, diagram: LaidOutDiagram, *, keep_unmoved_lines: bool = KEEP_UNMOVED_LINES,
) -> Arrangement:
    """Where everything *picture* draws goes once *diagram*'s layout is applied to it."""
    arranging = _Arranging(picture, diagram)
    relations, unroutable = arranging.relations(keep_unmoved_lines)
    return Arrangement(
        elements=arranging.elements,
        resized=frozenset(arranging.resized),
        boxes=arranging.boxes,
        relations=relations,
        paint_order=tuple(arranging.paint_order()),
        unroutable=unroutable,
    )
