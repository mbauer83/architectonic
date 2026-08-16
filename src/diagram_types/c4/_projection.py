"""C4 projection engine — the single membership+classification algorithm.

Owns all C4-specific connection-type constants and implements the C4
projection tables (system-context / container / component membership rules).
Both Seam B (strategy/refresh path) and Seam C (ViewProjector/preview path)
are produced here from one run.

The c4.scope-projection strategy that carries this to the refresh/diff path is declared in
`_manifest.py`, beside the registry it is for rather than beside the algorithm it runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.relationships.derivation_types import CandidateSet, ModelQuery
from src.domain.viewpoints.view_projection import ProjectedViewItem

_log = logging.getLogger(__name__)

_WARNING_THRESHOLD = 200
_MAX_ROLLUP_DEPTH = 8   # max nesting hops for roll-up traversal
_MAX_ITEMS = 150        # hard cap on projected items before warning becomes truncation

# ArchiMate structural (nesting) connection types.
# archimate-assignment included: active-structure "performs" behavior; in C4 terms the
# component owns its interface and assigned functions, so they roll into its boundary.
_NESTING_TYPES: frozenset[str] = frozenset({
    "archimate-composition", "archimate-aggregation", "archimate-assignment",
})
# ArchiMate dependency/flow connection types that project to c4-uses edges.
# archimate-association included for neighbour-discovery (interface→actor, interface→host);
# see _neighbor_entities for the root-level skip that prevents navigation-only links (AMP→AMS)
# from being treated as external neighbours.
_NEIGHBOR_TYPES: frozenset[str] = frozenset({
    "archimate-serving", "archimate-flow", "archimate-triggering",
    "archimate-access", "archimate-association",
})

# Allowed model entity types per C4 level and role.
#
# A service is never an external peer, at any level: it is behaviour the architecture provides,
# and drawing it with the external-system notation tells a reader the system depends on a third
# party that does not exist. The rule was established for the context level and spelled only
# there; the container and component neighbour sets kept `service` and so drew six of the
# platform's own application services as external systems the moment the model gained an edge
# reaching them. One rule, stated once here, for all three levels.
_EXTERNAL_PEER_TYPES: frozenset[str] = frozenset({
    "application-component", "business-actor", "role",
})
_CONTEXT_PROJ_TYPES: frozenset[str] = _EXTERNAL_PEER_TYPES | {"grouping"}
_CONTAINER_INTERNAL_TYPES: frozenset[str] = frozenset({
    "application-component", "service", "data-object", "node", "grouping",
})
_CONTAINER_NEIGHBOR_TYPES: frozenset[str] = _EXTERNAL_PEER_TYPES
_COMPONENT_INTERNAL_TYPES: frozenset[str] = frozenset({
    "application-component", "function", "service", "data-object", "grouping",
})
_COMPONENT_NEIGHBOR_TYPES: frozenset[str] = _EXTERNAL_PEER_TYPES | {"data-object"}


@dataclass(frozen=True)
class C4ProjectedItem:
    entity_id: str
    name: str
    artifact_type: str
    role: str       # "scope" | "internal" | "external"
    item_type: str  # C4 node type: "software-system", "container", "component", "person"


#: The portfolio altitude, named once: the only C4 type whose scope is a set rather than one entity.
LANDSCAPE_TYPE = "c4-system-landscape"

#: The other axis: where a system's containers run, rather than what they contain.
DEPLOYMENT_TYPE = "c4-deployment"

#: The levels whose scope is a drawn node rather than a boundary wrapper — so the scope entity is
#: part of what the diagram references. Spelled here beside the branches that classify those items,
#: which is the same place the render mode's consequences are already decided.
_SCOPE_DRAWN_TYPES: frozenset[str] = frozenset({LANDSCAPE_TYPE, "c4-system-context"})


@dataclass(frozen=True)
class C4Projection:
    """Result of project_c4: classified items + connection ids.

    diagram_type is stored so to_candidate_set() can decide whether to include the scope entities
    (they ARE visible nodes in system-landscape and system-context, but only a boundary wrapper in
    container/component).

    ``scope_of`` says which drawn scope item a *non*-drawn entity rolls up to — a structural
    descendant inside a system's boundary, whose edges to the outside are drawn on the boundary
    itself. One declared mapping in place of the "if this is the context level, everything falls
    back to the one root" rule the resolver used to carry, which could not have expressed a
    landscape's several roots at all.

    ``contained_by`` is the other structural fact a projection can carry: which *drawn* item holds
    another one inside it. Only the deployment view fills it, because only there does the diagram
    nest one drawn element in another — a container inside the node it runs on.
    """

    diagram_type: str
    items: tuple[C4ProjectedItem, ...]
    connection_ids: tuple[str, ...]
    scope_of: tuple[tuple[str, str], ...] = ()
    contained_by: tuple[tuple[str, str], ...] = ()

    def to_candidate_set(self) -> CandidateSet:
        """Seam B: membership-only set for the refresh/diff path."""
        include_scope = self.diagram_type in _SCOPE_DRAWN_TYPES
        entity_ids = frozenset(
            i.entity_id for i in self.items
            if i.role != "scope" or include_scope
        )
        return CandidateSet(entity_ids=entity_ids, connection_ids=frozenset(self.connection_ids))

    def to_view_items(self) -> list[ProjectedViewItem]:
        """Seam C: classified items (including scope root) for preview/renderer."""
        return [
            ProjectedViewItem(
                entity_id=i.entity_id,
                name=i.name,
                display_class=i.item_type,
                role=i.role,
            )
            for i in self.items
        ]


def _c4_item_type(
    role: str,
    artifact_type: str,
    scope_entity_type: str,
    internal_c4_type: str,
    person_archimate_types: frozenset[str],
) -> str:
    if role == "scope":
        return scope_entity_type
    if role == "internal":
        return internal_c4_type
    return "person" if artifact_type in person_archimate_types else "software-system"


def _entity_type(entity_id: str, query: ModelQuery) -> str:
    rec = query.get_entity(entity_id)
    return rec.artifact_type if rec else ""


def _make_item(
    entity_id: str,
    role: str,
    scope_entity_type: str,
    internal_c4_type: str,
    person_archimate_types: frozenset[str],
    query: ModelQuery,
) -> C4ProjectedItem:
    rec = query.get_entity(entity_id)
    name = rec.name if rec else entity_id
    artifact_type = rec.artifact_type if rec else ""
    item_type = _c4_item_type(role, artifact_type, scope_entity_type, internal_c4_type, person_archimate_types)
    return C4ProjectedItem(
        entity_id=entity_id, name=name, artifact_type=artifact_type,
        role=role, item_type=item_type,
    )


def _structural_children(root: str, max_depth: int, query: ModelQuery) -> set[str]:
    """BFS from root via nesting connection types (outbound) up to max_depth hops."""
    visited: set[str] = set()
    frontier: set[str] = {root}
    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for eid in frontier:
            for conn in query.find_connections_for(eid, direction="outbound"):
                if conn.conn_type in _NESTING_TYPES and conn.target not in visited:
                    visited.add(conn.target)
                    next_frontier.add(conn.target)
        frontier = next_frontier
        if not frontier:
            break
    return visited


def _neighbor_entities(
    scope: set[str],
    allowed_types: frozenset[str],
    query: ModelQuery,
    *,
    skip_association_from: str | None = None,
) -> set[str]:
    """Entities reachable from scope via _NEIGHBOR_TYPES, NOT in scope, with allowed type.

    skip_association_from: if set, archimate-association connections where *this* entity is
    the SOURCE are skipped.  Used to suppress outbound navigation-only links on the scope
    root (e.g. AMP --association→ AMS) without blocking inbound actor→system discovery.
    """
    result: set[str] = set()
    for eid in scope:
        for conn in query.find_connections_for(eid, direction="any"):
            if conn.conn_type not in _NEIGHBOR_TYPES:
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


def _direct_conns(projected: set[str], query: ModelQuery) -> set[str]:
    """_NEIGHBOR_TYPES connections where both source and target are in projected."""
    result: set[str] = set()
    for eid in projected:
        for conn in query.find_connections_for(eid, direction="outbound"):
            if conn.conn_type in _NEIGHBOR_TYPES and conn.target in projected:
                result.add(conn.artifact_id)
    return result


def _rollup_conns(internal: set[str], external: set[str], query: ModelQuery) -> set[str]:
    """Connection IDs between any internal entity and any external entity via _NEIGHBOR_TYPES.

    Used for bounded roll-up: collects model connections from any structural descendant
    to external neighbours so the renderer can map them onto the visible scope boundary.
    """
    result: set[str] = set()
    for eid in internal:
        for conn in query.find_connections_for(eid, direction="any"):
            if conn.conn_type not in _NEIGHBOR_TYPES:
                continue
            other = conn.target if conn.source == eid else conn.source
            if other in external:
                result.add(conn.artifact_id)
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
        return _make_item(eid, role, scope_entity_type, internal_c4_type, person_archimate_types, query)

    root_item = make(root_entity_id, "scope")
    # pre-compute full structural descendants for roll-up (all levels, used below)
    all_descendants = _structural_children(root_entity_id, _MAX_ROLLUP_DEPTH, query)
    scope_of: tuple[tuple[str, str], ...] = ()

    if diagram_type == "c4-system-context":
        # Roll-up: discover neighbours reachable from ANY internal descendant, not just root.
        # Root-level associations (AMP→AMS navigation link) are suppressed by skip_association_from.
        all_internal = {root_entity_id} | all_descendants
        neighbors = _neighbor_entities(
            all_internal, _CONTEXT_PROJ_TYPES, query,
            skip_association_from=root_entity_id,
        )
        neighbor_items = tuple(make(eid, "external") for eid in sorted(neighbors))
        items = (root_item, *neighbor_items)
        # Roll-up connections: any model connection between internal entities and neighbours.
        conn_ids = tuple(sorted(_rollup_conns(all_internal, neighbors, query)))
        scope_of = tuple((eid, root_entity_id) for eid in sorted(all_internal))

    elif diagram_type == "c4-container":
        raw_children = _structural_children(root_entity_id, 1, query)
        internal_ids = {e for e in raw_children if _entity_type(e, query) in _CONTAINER_INTERNAL_TYPES}
        scope_set = {root_entity_id} | internal_ids
        # use full descendants so deep sub-components can surface external neighbours.
        full_scope = {root_entity_id} | all_descendants
        neighbors = _neighbor_entities(
            full_scope, _CONTAINER_NEIGHBOR_TYPES, query,
            skip_association_from=root_entity_id,
        )
        internal_items = tuple(make(eid, "internal") for eid in sorted(internal_ids))
        neighbor_items = tuple(make(eid, "external") for eid in sorted(neighbors))
        all_displayed = scope_set | neighbors
        items = (root_item, *internal_items, *neighbor_items)
        conn_ids = tuple(sorted(
            _rollup_conns(full_scope, neighbors, query) | _direct_conns(all_displayed, query)
        ))

    elif diagram_type == "c4-component":
        raw_children = _structural_children(root_entity_id, 1, query)
        internal_ids = {e for e in raw_children if _entity_type(e, query) in _COMPONENT_INTERNAL_TYPES}
        scope_set = {root_entity_id} | internal_ids
        full_scope = {root_entity_id} | all_descendants
        neighbors = _neighbor_entities(
            full_scope, _COMPONENT_NEIGHBOR_TYPES, query,
            skip_association_from=root_entity_id,
        )
        internal_items = tuple(make(eid, "internal") for eid in sorted(internal_ids))
        neighbor_items = tuple(make(eid, "external") for eid in sorted(neighbors))
        all_displayed = scope_set | neighbors
        items = (root_item, *internal_items, *neighbor_items)
        conn_ids = tuple(sorted(
            _rollup_conns(full_scope, neighbors, query) | _direct_conns(all_displayed, query)
        ))

    else:
        return C4Projection(diagram_type=diagram_type, items=(), connection_ids=())

    # size limits — warn at threshold, truncate at hard cap
    if len(items) > _MAX_ITEMS:
        _log.warning(
            "C4 projection: %d items exceeds hard cap %d for scope %s — truncating",
            len(items), _MAX_ITEMS, root_entity_id,
        )
        items = items[:_MAX_ITEMS]
    elif len(items) > _WARNING_THRESHOLD:
        _log.warning(
            "C4 projection: %d items exceeds threshold %d for scope %s",
            len(items), _WARNING_THRESHOLD, root_entity_id,
        )

    return C4Projection(
        diagram_type=diagram_type, items=items, connection_ids=conn_ids, scope_of=scope_of
    )


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
        from src.diagram_types.c4._projection_deployment import project_c4_deployment  # noqa: PLC0415

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
        return _make_item(eid, role, scope_entity_type, scope_entity_type, person_archimate_types, query)

    scope_items = tuple(make(eid, "scope") for eid in root_entity_ids)
    internals_by_root = {
        root: {root} | _structural_children(root, _MAX_ROLLUP_DEPTH, query)
        for root in root_entity_ids
    }
    all_internal: set[str] = {eid for members in internals_by_root.values() for eid in members}

    neighbors = _neighbor_entities(all_internal, _CONTEXT_PROJ_TYPES, query) - all_internal
    neighbor_items = tuple(make(eid, "external") for eid in sorted(neighbors))

    conn_ids = tuple(sorted(
        _rollup_conns(all_internal, neighbors, query) | _direct_conns(all_internal, query)
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
