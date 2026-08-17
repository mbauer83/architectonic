"""C4 projection engine — the single membership+classification algorithm.

Implements the C4 projection tables (system-context / container / component membership rules) over
the vocabulary `_projection_vocabulary.py` declares. Both Seam B (strategy/refresh path) and Seam C
(ViewProjector/preview path) are produced here from one run.

The c4.scope-projection strategy that carries this to the refresh/diff path is declared in
`_manifest.py`, beside the registry it is for rather than beside the algorithm it runs.
"""

from __future__ import annotations

import logging

from src.diagram_types.c4._projection_deployment import project_c4_deployment
from src.diagram_types.c4._projection_grouping import grouping_membership, groupings_without_members
from src.diagram_types.c4._projection_neighbors import classify_neighbors
from src.diagram_types.c4._projection_rollup import (
    descendants,
    direct_conns,
    nearest_drawn_ancestor,
    rollup_conns,
)
from src.diagram_types.c4._projection_vocabulary import (
    CONTEXT_PROJ_TYPES,
    DEPLOYMENT_TYPE,
    EXTERNAL_PEER_TYPES,
    LANDSCAPE_TYPE,
    MAX_ROLLUP_DEPTH,
    NEIGHBOR_TYPES,
    NESTING_TYPES,
    ZOOM_INTERNAL_TYPES,
    C4ProjectedItem,
    C4Projection,
    entity_type,
    make_item,
)
from src.domain.relationships.derivation_types import ModelQuery

_log = logging.getLogger(__name__)

#: Beyond this many items a view has stopped being a view. The cap truncates and says so; the
#: threshold warns while the diagram is still drawable, so it has to sit *below* the cap to be
#: reachable at all. It was declared above it, which made its branch dead from the first commit.
_WARNING_THRESHOLD = 100
_MAX_ITEMS = 150


def _structural_children(root: str, max_depth: int, query: ModelQuery) -> set[str]:
    return descendants(root, query, nesting_types=NESTING_TYPES, max_depth=max_depth)


def _neighbor_entities(
    scope: set[str],
    allowed_types: frozenset[str],
    query: ModelQuery,
    *,
    skip_association_from: str | None = None,
) -> set[str]:
    """Entities reachable from scope via NEIGHBOR_TYPES, NOT in scope, with allowed type.

    skip_association_from: if set, archimate-association connections where *this* entity is
    the SOURCE are skipped.  Used to suppress outbound navigation-only links on the scope
    root (e.g. AMP --association→ AMS) without blocking inbound actor→system discovery.
    """
    result: set[str] = set()
    for eid in scope:
        for conn in query.find_connections_for(eid, direction="any"):
            if conn.conn_type not in NEIGHBOR_TYPES:
                continue
            if conn.conn_type == "archimate-association" and skip_association_from == conn.source:
                continue
            other = conn.target if conn.source == eid else conn.source
            if other in scope:
                continue
            rec = query.get_entity(other)
            if rec is not None and rec.artifact_type in allowed_types:
                result.add(other)
    return result


def project_c4(
    diagram_type: str,
    root_entity_id: str,
    query: ModelQuery,
    *,
    internal_c4_type: str,
    scope_entity_type: str,
    person_archimate_types: frozenset[str],
) -> C4Projection:
    """Single C4 projection algorithm for all diagram levels.

    Returns a C4Projection exposing two seams:
    - to_candidate_set(): for the refresh/diff path (membership only)
    - to_view_items(): for the preview checklist and renderer (classified)
    """
    def make(eid: str, role: str) -> C4ProjectedItem:
        return make_item(eid, role, scope_entity_type, internal_c4_type, person_archimate_types, query)

    root_item = make(root_entity_id, "scope")
    # pre-compute full structural descendants for roll-up (all levels, used below)
    all_descendants = _structural_children(root_entity_id, MAX_ROLLUP_DEPTH, query)
    scope_of: tuple[tuple[str, str], ...] = ()
    contained_by: tuple[tuple[str, str], ...] = ()

    if diagram_type == "c4-system-context":
        # Roll-up: discover neighbours reachable from ANY internal descendant, not just root.
        # Root-level associations (AMP→AMS navigation link) are suppressed by skip_association_from.
        all_internal = {root_entity_id} | all_descendants
        neighbors = _neighbor_entities(
            all_internal, CONTEXT_PROJ_TYPES, query,
            skip_association_from=root_entity_id,
        )
        neighbor_items = tuple(make(eid, "external") for eid in sorted(neighbors))
        items = (root_item, *neighbor_items)
        # Roll-up connections: any model connection between internal entities and neighbours.
        conn_ids = tuple(sorted(rollup_conns(all_internal, neighbors, query, dependency_types=NEIGHBOR_TYPES)))
        scope_of = tuple((eid, root_entity_id) for eid in sorted(all_internal))

    elif diagram_type in ZOOM_INTERNAL_TYPES:
        # One branch for both zoom levels. They differ in exactly one thing — which model types
        # count as the scope's own parts — and said it in two copies of the same twelve lines, which
        # is how the neighbour rule came to be stated twice and answered differently.
        raw_children = _structural_children(root_entity_id, 1, query)
        internal_ids = {
            e for e in raw_children if entity_type(e, query) in ZOOM_INTERNAL_TYPES[diagram_type]
        }
        # use full descendants so deep sub-components can surface external neighbours.
        full_scope = {root_entity_id} | all_descendants
        neighbors = _neighbor_entities(
            full_scope, EXTERNAL_PEER_TYPES, query,
            skip_association_from=root_entity_id,
        )
        contained_by = grouping_membership(internal_ids, query)
        internal_ids -= groupings_without_members(internal_ids, contained_by, query)
        scope_set = {root_entity_id} | internal_ids
        internal_items = tuple(make(eid, "internal") for eid in sorted(internal_ids))
        neighbor_items = classify_neighbors(
            root_entity_id, neighbors, query,
            scope_entity_type=scope_entity_type,
            internal_c4_type=internal_c4_type,
            person_archimate_types=person_archimate_types,
        )
        items = (root_item, *internal_items, *neighbor_items)
        # Over the scope's *whole* closure, not only what is drawn. `direct_conns` needs both
        # endpoints in the set it is given and `rollup_conns` needs one of them to be an external
        # neighbour, so a dependency between a drawn box and a deep descendant of *another* drawn
        # box fell through both and was never collected: the Artifact Index Store serves the SQLite
        # Indexer, which sits one level inside the Architecture Backend, and the container view drew
        # the store with no edges at all. Widening the input is safe because the rules are unchanged
        # — `direct_conns` still requires both ends present — and the resolver drops what rolls up
        # onto a single box as a self-loop.
        conn_ids = tuple(sorted(
            rollup_conns(full_scope, neighbors, query, dependency_types=NEIGHBOR_TYPES)
            | direct_conns(full_scope | neighbors, query, dependency_types=NEIGHBOR_TYPES)
        ))
        # Which drawn box speaks for each descendant the diagram does not draw. The zoom levels
        # left this empty, so the roll-up gathered a deep component's edges, the diagram recorded
        # them as used, and the resolver then dropped every one of them for want of an alias: 33 of
        # the 86 connections on the container view of this repository, among them Git Sync
        # Service's dependency on Git Hosting and the supply-chain connector's on its signal
        # sources.
        # Unlike the context level, the answer is not the root — a component three levels down
        # belongs on its own container, not on the system boundary above it. Where the only answer
        # IS the scope, the mapping still records it: the scope does contain the element, and it is
        # the *drawing* of an edge onto a boundary that the resolver declines, not the membership.
        scope_of = tuple(
            (eid, owner)
            for eid in sorted(all_descendants - scope_set)
            if (owner := nearest_drawn_ancestor(
                eid, scope_set, query,
                nesting_types=NESTING_TYPES, max_depth=MAX_ROLLUP_DEPTH,
            )) is not None
        )

    else:
        return C4Projection(diagram_type=diagram_type, items=(), connection_ids=())

    return C4Projection(
        diagram_type=diagram_type, items=_within_size_limits(items, root_entity_id),
        connection_ids=conn_ids, scope_of=scope_of, contained_by=contained_by,
    )


def _within_size_limits(
    items: tuple[C4ProjectedItem, ...], root_entity_id: str
) -> tuple[C4ProjectedItem, ...]:
    """Warn at the threshold, truncate at the cap — the one place either is decided."""
    if len(items) > _MAX_ITEMS:
        _log.warning(
            "C4 projection: %d items exceeds hard cap %d for scope %s — truncating",
            len(items), _MAX_ITEMS, root_entity_id,
        )
        return items[:_MAX_ITEMS]
    if len(items) > _WARNING_THRESHOLD:
        _log.warning(
            "C4 projection: %d items exceeds threshold %d for scope %s",
            len(items), _WARNING_THRESHOLD, root_entity_id,
        )
    return items


def project_c4_scope(
    diagram_type: str,
    root_entity_ids: tuple[str, ...],
    query: ModelQuery,
    *,
    internal_c4_type: str,
    scope_entity_type: str,
    person_archimate_types: frozenset[str],
) -> C4Projection:
    """The projection for a diagram's whole scope, however many entities it names.

    One dispatcher, because the resolver, the preview seam and the refresh strategy all have a
    diagram's scope in hand and each would otherwise decide for itself which projection a landscape
    takes — and a landscape that happens to name a single system must not fall through to the
    single-root algorithm, whose type table has no row for it.
    """
    if diagram_type == LANDSCAPE_TYPE:
        return project_c4_landscape(
            root_entity_ids, query,
            scope_entity_type=scope_entity_type,
            person_archimate_types=person_archimate_types,
        )
    if not root_entity_ids:
        return C4Projection(diagram_type=diagram_type, items=(), connection_ids=())
    if diagram_type == DEPLOYMENT_TYPE:
        return project_c4_deployment(
            root_entity_ids[0], query,
            internal_c4_type=internal_c4_type,
            scope_entity_type=scope_entity_type,
            person_archimate_types=person_archimate_types,
        )
    return project_c4(
        diagram_type, root_entity_ids[0], query,
        internal_c4_type=internal_c4_type,
        scope_entity_type=scope_entity_type,
        person_archimate_types=person_archimate_types,
    )


def project_c4_landscape(
    root_entity_ids: tuple[str, ...],
    query: ModelQuery,
    *,
    scope_entity_type: str,
    person_archimate_types: frozenset[str],
) -> C4Projection:
    """The portfolio altitude: several systems in scope at once, and what surrounds all of them.

    The same membership rule as the system context, applied to a set rather than a root. The
    difference that matters is what "external" means: at context level the peers are what one
    system touches, and here a peer of one scoped system may be another scoped system — so the
    scope set is subtracted from the neighbour set rather than only the single root's closure.
    """
    def make(eid: str, role: str) -> C4ProjectedItem:
        return make_item(eid, role, scope_entity_type, scope_entity_type, person_archimate_types, query)

    scope_items = tuple(make(eid, "scope") for eid in root_entity_ids)
    internals_by_root = {
        root: {root} | _structural_children(root, MAX_ROLLUP_DEPTH, query)
        for root in root_entity_ids
    }
    all_internal: set[str] = {eid for members in internals_by_root.values() for eid in members}

    neighbors = _neighbor_entities(all_internal, CONTEXT_PROJ_TYPES, query) - all_internal
    neighbor_items = tuple(make(eid, "external") for eid in sorted(neighbors))

    conn_ids = tuple(sorted(
        rollup_conns(all_internal, neighbors, query, dependency_types=NEIGHBOR_TYPES)
        | direct_conns(all_internal, query, dependency_types=NEIGHBOR_TYPES)
    ))
    scope_of = tuple(
        (eid, root)
        for root in root_entity_ids
        for eid in sorted(internals_by_root[root])
    )
    return C4Projection(
        diagram_type=LANDSCAPE_TYPE,
        items=(*scope_items, *neighbor_items),
        connection_ids=conn_ids,
        scope_of=scope_of,
    )
