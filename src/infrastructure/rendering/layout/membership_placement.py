"""Place newly drawn instances beside their neighbours and fit new boxes to the resulting picture."""

from collections.abc import Iterator, Mapping
from dataclasses import replace
from math import ceil, floor
from statistics import mean

from src.domain.diagrams.authored_groupings import is_rule_key
from src.domain.diagrams.layout.attachment import elements_crossed
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Layout, Placed
from src.domain.diagrams.layout.layout_checks import placed_extent
from src.domain.diagrams.layout.rendered_picture import RenderedPicture
from src.domain.diagrams.layout.route_quality import END_RUN
from src.domain.diagrams.layout.routing.router import route_all
from src.infrastructure.rendering.layout.arrangement import routing_input
from src.infrastructure.rendering.layout.box_identities import box_keys_by_alias


def _clear_positions(
    centre: Point, drawn: Extent, occupied: list[Extent], group: Extent | None,
) -> Iterator[Placed]:
    x, y = round(centre.x - drawn.width / 2), round(centre.y - drawn.height / 2)
    # Start as near the neighbour mean as the existing group allows. Expanding a
    # grouping moves its border and title and can cover an entirely unrelated endpoint.
    gx = round(min(max(x, group.left), group.right - drawn.width)) if group else x
    gy = round(min(max(y, group.top), group.bottom - drawn.height)) if group else y
    candidates = {(x, y), (gx, gy)}
    for box in occupied:
        left, right = floor(box.left - END_RUN - drawn.width), ceil(box.right + END_RUN)
        above, below = floor(box.top - END_RUN - drawn.height), ceil(box.bottom + END_RUN)
        candidates.update(((left, gy), (right, gy), (gx, above), (gx, below),
                           (left, round(box.top)), (right, round(box.top)),
                           (round(box.left), above), (round(box.left), below)))

    def preference(point: tuple[int, int]) -> tuple[float, float, tuple[int, int]]:
        left, top = point
        growth = 0.0 if group is None else (
            max(0, group.left - left) + max(0, left + drawn.width - group.right)
            + max(0, group.top - top) + max(0, top + drawn.height - group.bottom)
        )
        return growth, (left - x)**2 + (top - y)**2, point

    for left, top in sorted(candidates, key=preference):
        area = Extent(left - END_RUN, top - END_RUN, left + drawn.width + END_RUN, top + drawn.height + END_RUN)
        if all(area.overlap_with(box) is None for box in occupied):
            yield Placed(left, top)


def with_new_members(
    picture: RenderedPicture, diagram: LaidOutDiagram, new: frozenset[str],
) -> Layout:
    layout = diagram.layout
    keys = box_keys_by_alias(picture, diagram)
    present_boxes = set(keys.values())
    orphaned = frozenset(k for k in (*layout.boxes, *layout.z) if is_rule_key(k) and k not in present_boxes)
    layout = layout.without(boxes=orphaned)
    elements = dict(layout.elements)
    by_key = {key: alias for alias, key in diagram.instance_by_alias.items()}
    drawn = {key: extent for key, alias in by_key.items() if (extent := picture.extent_of(alias)) is not None}
    occupied = {key: placed_extent(place, (drawn[key].width, drawn[key].height)) or drawn[key]
                for key, place in elements.items() if key in drawn}
    occupied.update({key: extent for key, extent in drawn.items() if key not in new and key not in occupied})
    def choices(key: str, centre: Point, size: Extent) -> Iterator[Placed]:
        alias = by_key[key]
        ancestors = tuple(picture.boxes_around(alias))
        obstacles = [box for other, box in occupied.items() if other != key and by_key[other] not in ancestors
                     and alias not in picture.boxes_around(by_key[other])]
        group = next((extent for parent in ancestors if (stated := layout.boxes.get(keys.get(parent, "")))
                      and (extent := placed_extent(stated))), None)
        return _clear_positions(centre, size, obstacles, group)

    for key in sorted(new & drawn.keys() - elements.keys()):
        alias = by_key[key]
        neighbours = {diagram.instance_by_alias[b if a == alias else a]
                      for a, b in diagram.relations.values() if alias in (a, b)}
        centres = [occupied[n].centre for n in sorted(neighbours & occupied.keys())]
        centre = Point(mean(c.x for c in centres), mean(c.y for c in centres)) if centres else drawn[key].centre
        place = next(choices(key, centre, drawn[key]))
        elements[key] = place
        occupied[key] = Extent(place.x, place.y, place.x + drawn[key].width, place.y + drawn[key].height)
    layout = replace(layout, elements=elements)
    fitted = _fit_boxes(picture, diagram, keys, layout)
    if not new or not (blocked := _blocked(picture, diagram, fitted)):
        return fitted

    # The preview or the patch may already supply a position for a new member. Check
    # those positions too. Retained members and explicitly stated routes stay fixed.
    for key in sorted(new & drawn.keys()):
        current = elements[key]
        size = placed_extent(current, (drawn[key].width, drawn[key].height))
        assert size is not None
        for position in choices(key, size.centre, size):
            if (position.x, position.y) == (current.x, current.y):
                continue
            candidate = replace(current, x=position.x, y=position.y)
            trial = replace(layout, elements={**elements, key: candidate})
            fitted = _fit_boxes(picture, diagram, keys, trial)
            remaining = _blocked(picture, diagram, fitted)
            if not remaining:
                return fitted
            if remaining < blocked:
                elements[key] = candidate
                occupied[key] = Extent(position.x, position.y, position.x + size.width, position.y + size.height)
                blocked = remaining
                break
    names = [picture.label_of(end) or end for end in picture.relations[min(blocked)].ends]
    raise ValueError(f"No clear placement for the added members preserves the route between {' and '.join(names)}.")


def _blocked(picture: RenderedPicture, diagram: LaidOutDiagram, layout: Layout) -> set[int]:
    asked = routing_input(picture, replace(diagram, layout=layout))
    blocked = {int(index) for index in route_all(asked.scene, asked.connectors).unroutable}
    # A pinned course bypasses the search. A new shape still cannot sit across it.
    blocked.update(index for index, course in asked.stated.items()
                   if elements_crossed(course, asked.scene.elements, picture.relations[index].ends))
    return blocked


def _fit_boxes(
    picture: RenderedPicture, diagram: LaidOutDiagram, keys: Mapping[str, str], layout: Layout,
) -> Layout:
    scene = routing_input(picture, replace(diagram, layout=layout)).scene
    boxes = dict(layout.boxes)
    for alias, key in keys.items():
        if key not in boxes:
            extent = scene.boxes[alias]
            boxes[key] = Placed(round(extent.left), round(extent.top), ceil(extent.width), ceil(extent.height))
    return replace(layout, boxes=boxes)
