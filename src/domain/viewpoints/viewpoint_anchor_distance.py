"""Anchor-relative modeled distance for anchored execution results.

The distance a presentation may color/position by is the MODELED hop count between an
entity and the nearest anchor — a derived edge contributes its witness-chain length
(``hops``), never a flattened "one traversal step". The value is execution-scoped: it is
computed over the connections the execution actually returned, so it always agrees with
what the surface displays.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import Protocol


class AnchorIncidentEdge(Protocol):
    """The connection facts distance needs: endpoints, and the witness-chain length for
    derived edges (``None`` marks a modeled edge, whose length is by definition 1)."""

    @property
    def source(self) -> str: ...

    @property
    def target(self) -> str: ...

    @property
    def hops(self) -> int | None: ...


def anchor_modeled_distances(
    anchor_ids: Collection[str],
    connections: Iterable[AnchorIncidentEdge],
) -> dict[str, int]:
    """Minimum modeled distance from the nearest anchor, per entity that has one.

    An anchor ranks 0. A modeled edge to an anchor ranks its other endpoint 1; a derived
    edge ranks it at the edge's witness-chain length, with the minimum winning across all
    connecting edges and anchors. Entities with no edge to any anchor are absent from the
    result — unranked is a distinct state, never silently 0 or 1.
    """
    anchors = set(anchor_ids)
    distances: dict[str, int] = {anchor_id: 0 for anchor_id in anchors}
    for connection in connections:
        for endpoint, other in ((connection.source, connection.target), (connection.target, connection.source)):
            if endpoint not in anchors or other in anchors:
                continue
            length = 1 if connection.hops is None else connection.hops
            if length < distances.get(other, length + 1):
                distances[other] = length
    return distances
