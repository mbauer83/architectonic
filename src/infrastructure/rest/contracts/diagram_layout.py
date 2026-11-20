"""The contract a diagram's stated layout is served under.

Beside `diagrams`, which reads it: the block is geometry keyed by the identities a diagram already
uses, and its shape is `src.domain.diagrams.layout.layout_block`'s to decide. This mirrors that shape
for a client; a write sends the block as it is and the layout's own reader accepts or refuses it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


class LayoutPlacedContract(NullsOmitted):
    """Where a shape's top-left corner sits, and its size where the diagram states one."""

    x: int
    y: int
    w: int | None = None
    h: int | None = None


class LayoutPortContract(NullsOmitted):
    """Where a relation attaches: a side of its element and a fraction along it, from the top or left."""

    side: Literal["top", "right", "bottom", "left"]
    at: float


class LayoutLabelContract(NullsOmitted):
    """Where a relation's label sits: a fraction along its route and an offset from that point."""

    at: float
    dx: int = 0
    dy: int = 0


class LayoutRouteContract(NullsOmitted):
    """How one drawn relation runs; anything absent is the router's to decide."""

    model_config = ConfigDict(populate_by_name=True)

    from_: LayoutPortContract | None = Field(default=None, alias="from")
    to: LayoutPortContract | None = None
    via: list[tuple[int, int]] | None = None
    label: LayoutLabelContract | None = None


class DiagramLayoutContract(NullsOmitted):
    """A diagram's stated layout: geometry only, keyed by the identities the diagram already uses.

    ``elements`` by instance id (an entity's stable id, or an occurrence id); ``boxes`` by grouping
    id, or by rule key (``rule:domain=business``) for a box no grouping states; ``relations`` by the
    same key ``edge_key`` serves; ``z`` the stacking of any of the first two.
    """

    grid: int | None = None
    elements: dict[str, LayoutPlacedContract] | None = None
    boxes: dict[str, LayoutPlacedContract] | None = None
    relations: dict[str, LayoutRouteContract] | None = None
    z: dict[str, int] | None = None
