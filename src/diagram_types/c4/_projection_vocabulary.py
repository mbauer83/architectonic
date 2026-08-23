"""The terms C4 reads an ArchiMate model in, and the records those terms produce.

Every module that projects a level needs the same three things: which relation types nest and which
carry a dependency, which model types a level counts as its own parts, and how a classified item is
built. They lived in `_projection.py` beside the level algorithm, so each sibling imported them back
from the module that calls it — a cycle, paid for with a lazy in-function import and a lint
suppression at every one of the four call sites.

Nothing here decides membership. This is the vocabulary; `_projection.py` is the argument made in it.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.relationships.derivation_types import CandidateSet, ModelQuery
from src.domain.viewpoints.view_projection import ProjectedViewItem

#: How far a structural walk follows nesting before it stops looking.
MAX_ROLLUP_DEPTH = 8

# ArchiMate structural (nesting) connection types.
# archimate-assignment included: active-structure "performs" behavior; in C4 terms the
# component owns its interface and assigned functions, so they roll into its boundary.
NESTING_TYPES: frozenset[str] = frozenset({
    "archimate-composition", "archimate-aggregation", "archimate-assignment",
})
# ArchiMate dependency/flow connection types that project to c4-uses edges.
# archimate-association included for neighbour-discovery (interface→actor, interface→host);
# see _neighbor_entities for the root-level skip that prevents navigation-only links (AMP→AMS)
# from being treated as external neighbours.
NEIGHBOR_TYPES: frozenset[str] = frozenset({
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
EXTERNAL_PEER_TYPES: frozenset[str] = frozenset({
    "application-component", "business-actor", "role",
})
CONTEXT_PROJ_TYPES: frozenset[str] = EXTERNAL_PEER_TYPES | {"grouping"}
CONTAINER_INTERNAL_TYPES: frozenset[str] = frozenset({
    "application-component", "service", "data-object", "node", "grouping",
})
_COMPONENT_INTERNAL_TYPES: frozenset[str] = frozenset({
    "application-component", "function", "service", "data-object", "grouping",
})

#: What each zoom level counts as the scope's own parts — the only thing the two levels disagree
#: about. Their neighbour sets are both `EXTERNAL_PEER_TYPES`: a data object is not a neighbour at
#: either level. C4 draws stores as containers and the level below one has no notation for them at
#: all, so every data object a component *reached* arrived with the external-system shape, and the
#: backend's own thirteen indexes, config files and records were drawn as third-party systems it
#: depends on. State the scope actually contains still draws, through the table below; what is
#: withdrawn is the claim that state living elsewhere is somebody else's software.
ZOOM_INTERNAL_TYPES: dict[str, frozenset[str]] = {
    "c4-container": CONTAINER_INTERNAL_TYPES,
    "c4-component": _COMPONENT_INTERNAL_TYPES,
}

#: The model type that is a boundary rather than an element.
GROUPING_TYPE = "grouping"

#: What a grouping is drawn as, and it is deliberately not one of the element types. C4's own
#: definition is that a group "will be rendered as a boundary around those elements" and is a purely
#: visual construct — groups do not appear as elements in the model at all. Drawing one as a
#: component therefore states something C4 does not have a word for; drawing it as a boundary is the
#: whole of what it means. C4-PlantUML's generic `Boundary()` is the macro for it.
#:
#: Two consequences follow and are enforced where the members are chosen: a group holds elements of
#: **one** abstraction level, so a member the level does not draw is not in the boundary; and a group
#: with no drawn members is not drawn, because a boundary around nothing says nothing.
GROUP_TYPE = "group"

#: The portfolio altitude, named once: the only C4 type whose scope is a set rather than one entity.
LANDSCAPE_TYPE = "c4-system-landscape"

#: The other axis: where a system's containers run, rather than what they contain.
DEPLOYMENT_TYPE = "c4-deployment"

#: A deployment host — the C4 item type every technology element the deployment axis draws is given.
#: Named because three modules spelled it: the projection that builds the items, the resolver that
#: decides whether a technology name is worth showing beside it, and the renderer's macro table. The
#: macro table was the one that did not, and a host with nothing drawn inside it came out as an
#: application container.
NODE_TYPE = "node"

#: The levels whose scope is a drawn node rather than a boundary wrapper — so the scope entity is
#: part of what the diagram references. Spelled here beside the branches that classify those items,
#: which is the same place the render mode's consequences are already decided.
_SCOPE_DRAWN_TYPES: frozenset[str] = frozenset({LANDSCAPE_TYPE, "c4-system-context"})


@dataclass(frozen=True)
class C4ProjectedItem:
    entity_id: str
    name: str
    artifact_type: str
    role: str       # "scope" | "internal" | "peer" | "external"
    item_type: str  # C4 node type: "software-system", "container", "component", "person"


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
    another one inside it. Two levels fill it — the deployment view, where a container sits inside
    the node holding its artifact, and the zoom levels, where a grouping is the boundary its members
    are drawn within.
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


def is_externally_styled(role: str, item_type: str) -> bool:
    """Whether a projected item gets C4's external notation.

    `role` is membership — "outside the scope of this diagram". *External* is a claim: something
    you do not own or control. The two coincide for a system, because the scope set is the model's
    own statement of what is being documented, and a system outside it is somebody else's.

    They do not coincide for a person. The model has no way to say an actor is a foreigner —
    `external` is a property of a *standalone* diagram item, and `external-active-structure-element`
    is ArchiMate's word for an interface, not for a third party. Deriving it from role instead drew
    every actor in grey, which told a reader that nobody who uses the system belongs to the
    organisation, including the architects it is built for.

    Nor do they coincide for a sibling. Zooming into one container puts the rest of the same system
    outside the frame, which is membership and nothing more; `peer` is that case, and it carries the
    ordinary notation. Deriving external from role instead drew eleven of the platform's own
    containers as third-party systems on its component view — the same eleven the container view one
    level up draws inside the boundary.
    """
    return role == "external" and item_type != "person"


def entity_type(entity_id: str, query: ModelQuery) -> str:
    rec = query.get_entity(entity_id)
    return rec.artifact_type if rec else ""


def c4_item_type(
    role: str,
    artifact_type: str,
    scope_entity_type: str,
    internal_c4_type: str,
    person_archimate_types: frozenset[str],
) -> str:
    if role == "scope":
        return scope_entity_type
    if role in ("internal", "peer"):
        return GROUP_TYPE if artifact_type == GROUPING_TYPE else internal_c4_type
    return "person" if artifact_type in person_archimate_types else "software-system"


def make_item(
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
    item_type = c4_item_type(role, artifact_type, scope_entity_type, internal_c4_type, person_archimate_types)
    return C4ProjectedItem(
        entity_id=entity_id, name=name, artifact_type=artifact_type,
        role=role, item_type=item_type,
    )
