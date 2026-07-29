"""Derived-neighbor response construction shared by the connections endpoint."""

from __future__ import annotations

from src.application.runtime_catalogs import RuntimeCatalogs
from src.config.viewpoints_settings import (
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
)
from src.domain.relationships.relationship_reachability import (
    DerivationBounds,
    DerivationLimitError,
    RelationshipDerivationRequest,
    derive_relationships,
)
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess


def derive_neighbor_response(
    entity_id: str,
    *,
    max_hops: int,
    include_potential: bool,
    read_access: CriteriaReadAccess,
    catalogs: RuntimeCatalogs,
) -> dict[str, object]:
    """Return derived neighbors with the witness metadata needed by graph clients."""
    relationships = derive_relationships(
        RelationshipDerivationRequest(
            anchors=frozenset({entity_id}),
            direction="either",
            certainty="include_potential" if include_potential else "certain_only",
            bounds=DerivationBounds(
                max_hops=max_hops,
                max_relationships=viewpoints_derivation_max_relationships(),
                time_budget_seconds=viewpoints_derivation_time_budget_seconds(),
            ),
        ),
        read_access=read_access,
        registries=catalogs.module_catalog,
    ).relationships
    return {
        "traversal": "derived",
        "neighbors": [
            {
                "entity_id": relation.target_id if relation.source_id == entity_id else relation.source_id,
                "type": relation.connection_type,
                "certainty": relation.certainty,
                "hops": relation.hops,
                "via_connection_ids": list(relation.via_connection_ids),
                "path": relation.path_key,
            }
            for relation in relationships
        ],
    }


__all__ = ["DerivationLimitError", "derive_neighbor_response"]
