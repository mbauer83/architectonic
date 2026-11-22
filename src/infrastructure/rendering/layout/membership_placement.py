"""Place newly drawn instances beside their neighbours and fit new boxes to the resulting picture."""

from dataclasses import replace
from math import ceil, floor
from statistics import mean

from src.domain.diagrams.authored_groupings import is_rule_key
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Layout, Placed
from src.domain.diagrams.layout.layout_checks import placed_extent
from src.domain.diagrams.layout.rendered_picture import RenderedPicture
from src.domain.diagrams.layout.route_quality import END_RUN
from src.infrastructure.rendering.layout.arrangement import routing_input
from src.infrastructure.rendering.layout.box_identities import box_keys_by_alias


def _nearest_clear(centre: Point, drawn: Extent, occupied: list[Extent]) -> Placed:
    x, y = round(centre.x - drawn.width / 2), round(centre.y - drawn.height / 2)
    # Along either axis the closest free position is the starting point or an obstacle boundary.
    candidates = {(x, y)}
    for box in occupied:
        candidates.update((
            (ceil(box.right + END_RUN), y), (floor(box.left - END_RUN - drawn.width), y),
            (x, ceil(box.bottom + END_RUN)), (x, floor(box.top - END_RUN - drawn.height)),
        ))
    for left, top in sorted(candidates, key=lambda p: ((p[0] - x)**2 + (p[1] - y)**2, p)):
        area = Extent(left - END_RUN, top - END_RUN, left + drawn.width + END_RUN, top + drawn.height + END_RUN)
        if all(area.overlap_with(box) is None for box in occupied):
            return Placed(left, top)
    raise AssertionError("The outermost obstacle boundary is always free")


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
    for key in sorted(new & drawn.keys() - elements.keys()):
        alias = by_key[key]
        neighbours = {diagram.instance_by_alias[b if a == alias else a]
                      for a, b in diagram.relations.values() if alias in (a, b)}
        centres = [occupied[n].centre for n in sorted(neighbours & occupied.keys())]
        centre = Point(mean(c.x for c in centres), mean(c.y for c in centres)) if centres else drawn[key].centre
        ancestors = set(picture.boxes_around(by_key[key]))
        obstacles = [box for other, box in occupied.items() if by_key[other] not in ancestors
                     and by_key[key] not in picture.boxes_around(by_key[other])]
        place = _nearest_clear(centre, drawn[key], obstacles)
        elements[key] = place
        occupied[key] = Extent(place.x, place.y, place.x + drawn[key].width, place.y + drawn[key].height)
    layout = replace(layout, elements=elements)
    scene = routing_input(picture, replace(diagram, layout=layout)).scene
    boxes = dict(layout.boxes)
    for alias, key in keys.items():
        if key not in boxes and is_rule_key(key):
            extent = scene.boxes[alias]
            boxes[key] = Placed(round(extent.left), round(extent.top), ceil(extent.width), ceil(extent.height))
    return replace(layout, boxes=boxes)
