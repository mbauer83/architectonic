"""What a neighbour *is* to the diagram that found it.

Membership — who is outside the scope — belongs to `_projection.py`, which walks the graph. This is
the question that comes after: of the things outside the frame, which are somebody else's software
and which are simply the rest of the same system. C4 draws those two with different notation, and
answering it needs an upward walk that the membership rules never take.
"""

from __future__ import annotations

from src.diagram_types.c4._projection_rollup import descendants, topmost_ancestor
from src.diagram_types.c4._projection_vocabulary import (
    MAX_ROLLUP_DEPTH,
    NESTING_TYPES,
    C4ProjectedItem,
    make_item,
)
from src.domain.relationships.derivation_types import ModelQuery


def _family_of(owner: str, query: ModelQuery, depth: int) -> set[str]:
    return descendants(owner, query, nesting_types=NESTING_TYPES, max_depth=depth)


def classify_neighbors(
    root_entity_id: str,
    neighbors: set[str],
    query: ModelQuery,
    *,
    scope_entity_type: str,
    internal_c4_type: str,
    person_archimate_types: frozenset[str],
) -> tuple[C4ProjectedItem, ...]:
    """Split the neighbour set into siblings of the scope and genuine outsiders.

    A neighbour inside the same owning system is a `peer`: outside this diagram's frame, but not
    somebody else's software. Its C4 type is what the system makes it — a direct child of the owner
    is a container, anything deeper is a component, and the owner itself is the system.

    Stated once and applied at every level, though only the component level can produce a peer at
    all: everywhere else the scope root is already the topmost system, so its whole tree is
    subtracted from the neighbour set before this sees it, and the walk stops at the first hop.
    """
    owner = topmost_ancestor(
        root_entity_id, query, nesting_types=NESTING_TYPES, max_depth=MAX_ROLLUP_DEPTH,
    )
    if owner == root_entity_id:
        return tuple(
            make_item(eid, "external", scope_entity_type, internal_c4_type, person_archimate_types, query)
            for eid in sorted(neighbors)
        )
    family = _family_of(owner, query, MAX_ROLLUP_DEPTH) | {owner}
    owner_children = _family_of(owner, query, 1)
    items: list[C4ProjectedItem] = []
    for eid in sorted(neighbors):
        if eid not in family:
            items.append(make_item(
                eid, "external", scope_entity_type, internal_c4_type, person_archimate_types, query,
            ))
            continue
        if eid == owner:
            peer_type = scope_entity_type
        else:
            peer_type = "container" if eid in owner_children else internal_c4_type
        items.append(make_item(
            eid, "peer", scope_entity_type, peer_type, person_archimate_types, query,
        ))
    return tuple(items)
