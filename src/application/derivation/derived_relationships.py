"""derived-relationships/v1 strategy: candidate set = entities/connections reachable
from ``root_entity_ids`` via bounded relationship derivation (Appendix B) — modeled
connections along witness chains flow through by id; derived relationships flow through
as candidate witness paths, never as synthetic connection ids (the standing "derived
relationships are never persisted" invariant). Same acceptance defaults as
``viewpoint_execution``: certain candidates pre-included, potential ones pre-excluded
until explicitly accepted.

Pure application logic only: ``catalog`` (the ontology ``ModuleCatalog`` the derivation
engine reads its rule tables from) is injected by the composition-root registration
closure (``src.infrastructure.derivation_strategy_wiring``) — a ``ModelQuery``-only
``derive_fn`` cannot build one itself (ontology-catalog construction lives at the
composition root; same gap, same resolution, as ``viewpoint_execution``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.application.derivation.types import CandidateSet
from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.relationships.derivation_types import StrategySpec
from src.domain.relationships.relationship_reachability import (
    DerivationBounds,
    DerivationCertaintyPolicy,
    DerivedRelationship,
    RelationshipDerivationRequest,
    derive_relationships,
)
from src.domain.viewpoints.view_derivations import DerivationSelection, PathProvenance
from src.domain.viewpoints.viewpoint_criteria import IncidentDirection
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess

SPEC = StrategySpec(
    name="derived_relationships",
    version=1,
    supported_filters=frozenset({"direction", "include_potential", "max_hops"}),
)


def _roots(params: Mapping[str, object]) -> frozenset[str]:
    raw = params.get("root_entity_ids")
    return frozenset(str(r) for r in raw) if isinstance(raw, list) else frozenset()


def _direction(params: Mapping[str, object]) -> IncidentDirection:
    raw = params.get("direction", "either")
    if raw not in ("outgoing", "incoming", "either"):
        return "either"
    return raw


def _certainty(params: Mapping[str, object]) -> DerivationCertaintyPolicy:
    return "include_potential" if params.get("include_potential") else "certain_only"


def _path_key(synthetic_relationship_id: str) -> str:
    """Recover the canonical witness-path key from a derived relationship's synthetic id
    (``derived::<type-slug>::<path-key>``)."""
    return synthetic_relationship_id.split("::", 2)[2]


def _derive(
    params: Mapping[str, object],
    *,
    read_access: CriteriaReadAccess,
    catalog: ModuleCatalog,
    default_max_hops: int,
    max_relationships: int,
    time_budget_seconds: float = 2.0,
) -> tuple[DerivedRelationship, ...]:
    roots = _roots(params)
    if not roots:
        return ()
    max_hops_raw = params.get("max_hops")
    max_hops = int(max_hops_raw) if isinstance(max_hops_raw, (int, float)) else default_max_hops
    bounds = DerivationBounds(max_hops, max_relationships, time_budget_seconds)
    request = RelationshipDerivationRequest(roots, _direction(params), _certainty(params), bounds)
    return derive_relationships(request, read_access=read_access, registries=catalog).relationships


@dataclass(frozen=True)
class _Collected:
    entity_ids: frozenset[str]
    connection_ids: frozenset[str]
    certain_paths: tuple[str, ...]
    potential_paths: tuple[str, ...]
    provenance: Mapping[str, PathProvenance]


def _collect(relationships: tuple[DerivedRelationship, ...], *, read_access: CriteriaReadAccess) -> _Collected:
    """Reachable entities include every witness-chain hop, not just each derived
    relationship's own endpoints — a witness connection is only displayable if both of
    its own endpoints are in the included entity set (the structural invariant every
    other consumer of a candidate set relies on)."""
    entity_ids: set[str] = set()
    connection_ids: set[str] = set()
    certain_paths: list[str] = []
    potential_paths: list[str] = []
    provenance: dict[str, PathProvenance] = {}
    for relationship in relationships:
        entity_ids.add(relationship.source_id)
        entity_ids.add(relationship.target_id)
        for connection_id in relationship.via_connection_ids:
            connection_ids.add(connection_id)
            connection = read_access.get_connection(connection_id)
            if connection is not None:
                entity_ids.add(connection.source)
                entity_ids.add(connection.target)
        path_key = _path_key(relationship.artifact_id)
        (certain_paths if relationship.certainty == "certain" else potential_paths).append(path_key)
        provenance[path_key] = PathProvenance(
            certainty=relationship.certainty, connection_type=relationship.connection_type
        )
    return _Collected(
        entity_ids=frozenset(entity_ids),
        connection_ids=frozenset(connection_ids),
        certain_paths=tuple(sorted(certain_paths)),
        potential_paths=tuple(sorted(potential_paths)),
        provenance=provenance,
    )


def evaluate_candidates(
    params: Mapping[str, object],
    *,
    read_access: CriteriaReadAccess,
    catalog: ModuleCatalog,
    default_max_hops: int,
    max_relationships: int,
) -> CandidateSet:
    relationships = _derive(
        params, read_access=read_access, catalog=catalog, default_max_hops=default_max_hops,
        max_relationships=max_relationships,
    )
    collected = _collect(relationships, read_access=read_access)
    return CandidateSet(
        entity_ids=collected.entity_ids | _roots(params),
        connection_ids=collected.connection_ids,
        paths=frozenset(collected.certain_paths) | frozenset(collected.potential_paths),
    )


def default_selection(
    params: Mapping[str, object],
    *,
    read_access: CriteriaReadAccess,
    catalog: ModuleCatalog,
    default_max_hops: int,
    max_relationships: int,
) -> DerivationSelection:
    """Initial acceptance state for a freshly generated diagram."""
    relationships = _derive(
        params, read_access=read_access, catalog=catalog, default_max_hops=default_max_hops,
        max_relationships=max_relationships,
    )
    collected = _collect(relationships, read_access=read_access)
    return DerivationSelection(
        included_entity_ids=tuple(sorted(collected.entity_ids | _roots(params))),
        included_connection_ids=tuple(sorted(collected.connection_ids)),
        included_paths=collected.certain_paths,
        excluded_paths=collected.potential_paths,
        path_provenance=collected.provenance,
    )
