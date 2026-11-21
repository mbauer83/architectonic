"""The layout first written down for a diagram: the renderer's arrangement, with room made for its lines.

A diagram takes a layout over from the picture the renderer drew of it. Written down as drawn, its
gaps between boxes are the renderer's, made for curves, and often too narrow for the lines the router
lays along them. So the first layout is the drawn arrangement **widened** (`routing.widening`): each
channel too narrow for its lines opened by what it lacks, boxes kept in their order and nesting. That
happens here, once; afterwards nothing moves that the layout's author did not move, and a channel
still too narrow is the verifier's to report (W384).

Every element is placed at its corner, every box the layout can name — a grouping by its id, a computed
box by its rule, an element holding its parts as an element — at its corner and size. Relations are
not stated: every one is routed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.layout_block import Layout, Placed
from src.domain.diagrams.layout.rendered_picture import RenderedPicture
from src.domain.diagrams.layout.routing.scene import RoutingScene
from src.domain.diagrams.layout.routing.widening import widened
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
    """The layout that writes *picture*'s arrangement down for *diagram*, its narrow channels widened.

    Whatever *diagram* states already is not consulted: this is the layout a diagram starts from. The
    arrangement is written down in whole pixels first and widened from there, so the channels measured
    are the ones the written layout draws.
    """
    unstated = replace(diagram, layout=Layout())
    keys = box_keys_by_alias(picture, unstated)
    as_drawn = _written(diagram, keys, routing_input(picture, unstated).scene)
    asked = routing_input(picture, replace(diagram, layout=as_drawn))
    return _written(diagram, keys, widened(asked.scene, asked.connectors))
