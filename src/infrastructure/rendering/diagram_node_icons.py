"""Which embedded icon each node of a diagram-owned notation shows, by the alias it is declared under.

For a notation whose elements the diagram itself hosts — C4's people, systems and containers — an
instance is a node of `diagram-entities`, named by its local id, and its type is the node's type. The
precedence is the generic one (`application.icons.effective_icons`); a node carries no specialization,
so the levels are the node's own assignment and its type's. The renderer states how large it draws.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.application.icons.effective_icons import effective_icon, icon_assignments
from src.application.puml_icon_header import icon_key, icon_reference, sprite_reference, with_icon_block
from src.domain.icons.resolved_icon import IconSource


@dataclass(frozen=True, slots=True)
class DrawnNode:
    """One node as the renderer declares it: the id statements name it by, its type, its alias."""

    local_id: str
    node_type: str
    alias: str


@dataclass(frozen=True, slots=True)
class NodeIcons:
    #: alias → the icon as a macro's image parameter shows it (C4's `$sprite`).
    sprites: Mapping[str, str]
    #: alias → the icon as a title that takes no image parameter opens with.
    badges: Mapping[str, str]
    #: icon key → the picture the body's icon block embeds under it.
    pictures: Mapping[str, bytes]

    def embedded_in(self, body: str) -> str:
        """*body* with the icon block its references need."""
        return with_icon_block(body, self.pictures)


def node_icons(
    diagram_entities: Mapping[str, object] | None,
    nodes: Sequence[DrawnNode],
    source: IconSource | None,
    drawn_px: int,
) -> NodeIcons:
    if source is None:
        return NodeIcons({}, {}, {})
    assignments = icon_assignments(diagram_entities)
    sprites: dict[str, str] = {}
    badges: dict[str, str] = {}
    pictures: dict[str, bytes] = {}
    for node in nodes:
        shown = effective_icon(node.local_id, (node.node_type,), assignments, source)
        if shown is None:
            continue
        key = icon_key(shown.icon.render_digest)
        scale = f"{drawn_px / max(shown.icon.width, shown.icon.height):.3g}"
        sprites[node.alias], badges[node.alias] = sprite_reference(key, scale), icon_reference(key, scale)
        pictures[key] = shown.icon.png
    return NodeIcons(sprites, badges, pictures)
