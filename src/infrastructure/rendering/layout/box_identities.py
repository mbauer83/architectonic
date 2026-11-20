"""Which box of a picture each box key of a layout addresses.

A layout sizes a box by the identity the diagram gives it: a grouping by its id, a box the renderer
computes by its rule. A picture knows a box only by alias. The join is made from the picture itself
rather than by recomputing the renderer's numbering: a stated grouping is the nearest grouping box
around one of its own members, and a computed box is told by what is drawn inside it — a domain's box
holds elements of that domain, a type's box elements of that type within it.

Two boxes one rule path draws — a type boxed once per flow of a canvas — are told apart by their
order on the picture, which is what a rule key's ordinal counts.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from src.domain.diagrams.authored_groupings import GroupingRule, RuleKey
from src.domain.diagrams.layout.box_aliases import BoxKind
from src.domain.diagrams.layout.laid_out_diagram import DrawnKind, LaidOutDiagram, StatedGrouping
from src.domain.diagrams.layout.rendered_picture import RenderedPicture


def _grouping_box_around(picture: RenderedPicture, diagram: LaidOutDiagram, alias: str) -> str | None:
    """The nearest box around *alias* that is a grouping an author made, not an element and not computed."""
    return next(
        (
            box for box in picture.boxes_around(alias)
            if picture.boxes[box].kind(element_aliases=diagram.instance_by_alias) is BoxKind.AUTHORED_GROUPING
        ),
        None,
    )


def _stated_boxes(
    picture: RenderedPicture, diagram: LaidOutDiagram, grouping: StatedGrouping
) -> Iterator[tuple[str, str]]:
    """Each stated grouping's box alias with its id, subgroups before the grouping that holds them."""
    inner = [found for group in grouping.groups for found in _stated_boxes(picture, diagram, group)]
    yield from inner
    own = next(
        (box for member in grouping.members if (box := _grouping_box_around(picture, diagram, member))), None
    )
    if own is None:
        # A grouping with no member of its own is the box around its first drawn subgroup.
        subgroup_ids = {group.grouping_id for group in grouping.groups}
        own = next(
            (
                outer for alias, grouping_id in inner
                if grouping_id in subgroup_ids and (outer := _grouping_box_around(picture, diagram, alias))
            ),
            None,
        )
    if own is not None and grouping.grouping_id:
        yield own, grouping.grouping_id


def _kind_drawn_inside(picture: RenderedPicture, diagram: LaidOutDiagram, box: str) -> DrawnKind | None:
    """What the first element drawn anywhere inside *box* is, where the diagram tells."""
    return next(
        (
            diagram.kinds[alias]
            for alias in (*picture.elements, *picture.boxes)
            if alias in diagram.kinds and box in picture.boxes_around(alias)
        ),
        None,
    )


def _computed_boxes(picture: RenderedPicture, diagram: LaidOutDiagram) -> Iterator[tuple[str, str]]:
    """Each computed box's alias with the rule key that addresses it."""
    drawn_so_far: dict[tuple[GroupingRule, ...], int] = defaultdict(int)
    for alias, box in picture.boxes.items():
        kind = box.kind(element_aliases=diagram.instance_by_alias)
        inside = _kind_drawn_inside(picture, diagram, alias)
        if inside is None or kind not in (BoxKind.DOMAIN, BoxKind.TYPE):
            continue
        domain = GroupingRule("domain", inside.domain)
        path = (domain,) if kind is BoxKind.DOMAIN else (domain, GroupingRule("type", inside.element_type))
        drawn_so_far[path] += 1
        yield alias, RuleKey(path, drawn_so_far[path]).text


def box_keys_by_alias(picture: RenderedPicture, diagram: LaidOutDiagram) -> dict[str, str]:
    """The layout key of every box of *picture* that has one: a grouping's id, or a computed box's rule."""
    keys = dict(found for grouping in diagram.groupings for found in _stated_boxes(picture, diagram, grouping))
    if diagram.boxes_are_computed:
        keys.update(_computed_boxes(picture, diagram))
    return keys
