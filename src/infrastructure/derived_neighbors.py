"""An entity's derived neighbours: the one reading the REST route and the MCP tool both serve.

Both surfaces used to build the derivation request and shape its rows themselves, and the two copies
were held together only by a test asserting their answers matched. A field added to one would have
been a difference the other did not have, so the request and the row live here.
"""

from __future__ import annotations

from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
)
from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.relationships.relationship_reachability import (
    DerivationBounds,
    DerivationLimitError,
    DerivedRelationship,
    RelationshipDerivationRequest,
    derive_relationships,
)
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess


def derived_neighbor_row(
    relationship: DerivedRelationship, entity_id: str, read_access: CriteriaReadAccess
) -> dict[str, object]:
    """One derived relationship as seen from *entity_id*: the other end, and which way it runs.

    ``direction`` is the relationship's model direction relative to the entity read, in the
    vocabulary the connection reads already use (``outbound`` / ``inbound``). Without it a reader
    could not tell what leads to an entity from what it leads to. ``entity_name`` is the other end's
    name, because a derived end is usually one the reader has nothing else open for.
    """
    outbound = relationship.source_id == entity_id
    other = relationship.target_id if outbound else relationship.source_id
    record = read_access.get_entity(other)
    return {
        "entity_id": other,
        "entity_name": record.name if record is not None else other,
        "type": relationship.connection_type,
        "direction": "outbound" if outbound else "inbound",
        "certainty": relationship.certainty,
        "hops": relationship.hops,
        "via_connection_ids": list(relationship.via_connection_ids),
        "path": relationship.path_key,
    }


def derive_neighbors(
    entity_id: str,
    *,
    max_hops: int | None,
    include_potential: bool,
    read_access: CriteriaReadAccess,
    registries: ModuleCatalog,
) -> list[dict[str, object]]:
    """The relationships the derivation composes from *entity_id*, either way, as neighbour rows.

    *max_hops* left unset is the configured derivation bound — the same bound a viewpoint derives
    within — so a caller asking "what does the model imply here?" need not restate it.
    """
    relationships = derive_relationships(
        RelationshipDerivationRequest(
            anchors=frozenset({entity_id}),
            direction="either",
            certainty="include_potential" if include_potential else "certain_only",
            bounds=DerivationBounds(
                max_hops=max_hops if max_hops is not None else viewpoints_derivation_max_hops(),
                max_relationships=viewpoints_derivation_max_relationships(),
                time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
            ),
        ),
        read_access=read_access,
        registries=registries,
    ).relationships
    return [derived_neighbor_row(relationship, entity_id, read_access) for relationship in relationships]


__all__ = ["DerivationLimitError", "derive_neighbors", "derived_neighbor_row"]
