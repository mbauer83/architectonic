"""The layout first written down for a diagram: the renderer's arrangement, as it was drawn.

A diagram takes a layout over from the picture the renderer drew of it, and keeps that picture's lines
(owner, 2026-11-25): a line nothing moved touches stays as it was drawn (`routing.kept`), so no room has
to be made for the router before anything moves. Afterwards nothing moves that the layout's author did
not move, and a channel too narrow for the lines routed along it is the verifier's to report (W384).

Every element is placed at its corner, every box the layout can name — a grouping by its id, a computed
box by its rule, an element holding its parts as an element — at its corner and size, in whole pixels.
Relations are not stated.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Layout, Placed
from src.domain.diagrams.layout.rendered_picture import RenderedPicture
from src.domain.diagrams.layout.routing.scene import RoutingScene
from src.infrastructure.rendering.layout.arrangement import routing_input
from src.infrastructure.rendering.layout.box_identities import box_keys_by_alias


def _sized(extent: Extent) -> Placed:
    return Placed(round(extent.left), round(extent.top), max(1, round(extent.width)), max(1, round(extent.height)))


def _written(diagram: LaidOutDiagram, keys: Mapping[str, str], scene: RoutingScene) -> Layout:
    """*scene*'s shapes as a layout writes them: in whole pixels, each by the identity the diagram uses."""
    instance_of = diagram.instance_by_alias
    elements = {
        instance_of[alias]: Placed(round(extent.left), round(extent.top))
        for alias, extent in scene.elements.items() if alias in instance_of
    }
    elements.update({
        instance_of[alias]: _sized(extent) for alias, extent in scene.boxes.items() if alias in instance_of
    })
    boxes = {
        keys[alias]: _sized(extent)
        for alias, extent in scene.boxes.items() if alias not in instance_of and alias in keys
    }
    return Layout(elements=elements, boxes=boxes)


def first_layout(picture: RenderedPicture, diagram: LaidOutDiagram) -> Layout:
    """The layout that writes *picture*'s arrangement down for *diagram*, as drawn.

    Whatever *diagram* states already is not consulted: this is the layout a diagram starts from.
    """
    unstated = replace(diagram, layout=Layout())
    return _written(diagram, box_keys_by_alias(picture, unstated), routing_input(picture, unstated).scene)
