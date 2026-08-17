"""Structural walks over the model graph, and what they make visible.

The relation vocabulary is passed in rather than imported: nothing here knows what C4 is, so the
caller owns the question of which relation types nest and which carry a dependency. That is also why
every other projection module can depend on this one without a cycle.

Three of the four walks below are the *same* walk. `_ancestry` climbs the nesting relation once, and
"the topmost owner" and "the nearest drawn owner" are two stopping rules over it — they were written
twice, in two modules, with two spellings of the cycle guard.
"""

from __future__ import annotations

from collections.abc import Iterator

from src.domain.relationships.derivation_types import ModelQuery


def _ancestry(
    entity_id: str, query: ModelQuery, *, nesting_types: frozenset[str], max_depth: int
) -> Iterator[str]:
    """Each structural parent in turn, nearest first, for at most *max_depth* hops.

    Stops on a repeat, because a containment cycle is a modelling error rather than a reason to
    loop. Where an entity has several parents the first the index reports is followed: a C4 box is
    drawn in one place, so a second home would have to be discarded further up anyway.
    """
    seen = {entity_id}
    current = entity_id
    for _ in range(max_depth):
        parent = next(
            (
                conn.source
                for conn in query.find_connections_for(current, direction="inbound")
                if conn.conn_type in nesting_types and conn.source not in seen
            ),
            None,
        )
        if parent is None:
            return
        yield parent
        seen.add(parent)
        current = parent


def descendants(
    root: str, query: ModelQuery, *, nesting_types: frozenset[str], max_depth: int
) -> set[str]:
    """Everything structurally inside *root*, to *max_depth* hops — breadth-first, root excluded."""
    visited: set[str] = set()
    frontier: set[str] = {root}
    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for eid in frontier:
            for conn in query.find_connections_for(eid, direction="outbound"):
                if conn.conn_type in nesting_types and conn.target not in visited:
                    visited.add(conn.target)
                    next_frontier.add(conn.target)
        frontier = next_frontier
        if not frontier:
            break
    return visited


def topmost_ancestor(
    entity_id: str, query: ModelQuery, *, nesting_types: frozenset[str], max_depth: int
) -> str:
    """The outermost thing holding *entity_id* — the system a container belongs to.

    Returns *entity_id* itself when nothing holds it, which is what every level but the component
    one sees: their scope root is already the system.
    """
    chain = list(_ancestry(entity_id, query, nesting_types=nesting_types, max_depth=max_depth))
    return chain[-1] if chain else entity_id


def nearest_drawn_ancestor(
    entity_id: str,
    drawn: set[str],
    query: ModelQuery,
    *,
    nesting_types: frozenset[str],
    max_depth: int,
) -> str | None:
    """The closest structural ancestor of *entity_id* that is in *drawn*.

    What a roll-up needs, and what naming a scope root can only approximate. Where a diagram draws
    one box, every descendant rolls up to it and the root is the whole answer; where a diagram draws
    the root's children too, an edge from three levels down belongs on *its* parent box, not on the
    boundary above it.

    Answers None when nothing on the way up is drawn — an entity the diagram cannot speak for.
    """
    return next(
        (
            parent
            for parent in _ancestry(entity_id, query, nesting_types=nesting_types, max_depth=max_depth)
            if parent in drawn
        ),
        None,
    )


def direct_conns(
    projected: set[str], query: ModelQuery, *, dependency_types: frozenset[str]
) -> set[str]:
    """Connections of a dependency type whose source and target are both drawn."""
    return {
        conn.artifact_id
        for eid in projected
        for conn in query.find_connections_for(eid, direction="outbound")
        if conn.conn_type in dependency_types and conn.target in projected
    }


def rollup_conns(
    internal: set[str], external: set[str], query: ModelQuery, *, dependency_types: frozenset[str]
) -> set[str]:
    """Connections between anything inside the scope and anything outside it.

    Collected over the scope's *full* descendant set rather than only what is drawn, so a dependency
    a deep part has on the outside world can be raised onto the box that stands for it.
    """
    return {
        conn.artifact_id
        for eid in internal
        for conn in query.find_connections_for(eid, direction="any")
        if conn.conn_type in dependency_types
        and (conn.target if conn.source == eid else conn.source) in external
    }
