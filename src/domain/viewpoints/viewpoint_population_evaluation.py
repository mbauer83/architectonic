"""Population-level evaluation: widening the primary
entity population via ``NeighborInclusion`` terms, and selecting the connections displayed
for a resolved entity population (the ordinary structural invariant and the sharper matrix
bridging form). Built entirely on the pure per-record predicates in
``viewpoint_criteria_evaluation.py`` — no independent evaluation logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.ontology_representation.artifact_types import ConnectionRecord
from src.domain.relationships.relationship_reachability import (
    DerivationBounds,
    DerivedRelationship,
    RelationshipDerivationRequest,
    derive_relationships,
)
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import ConnectionSelection, NeighborInclusion
from src.domain.viewpoints.viewpoint_criteria_evaluation import (
    _derived_matches,
    direction_matches,
    evaluate_connection_criteria,
    evaluate_entity_criteria,
)
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess, EvaluationEnvironment


@dataclass(frozen=True)
class NeighborInclusionResult:
    """Entities widened into the population (membership precedence: an entity already in
    the primary set is never re-added here; entities matched by several inclusion terms
    appear once)."""

    expanded_ids: frozenset[str]
    schema_drift: frozenset[str] = frozenset()
    # True when a `traversal: derived` inclusion term's search hit its time budget before
    # finishing — `expanded_ids` is a genuine, correct partial result (nothing incorrect was
    # included), just not necessarily the complete reachable set.
    derivation_truncated: bool = False


@dataclass(frozen=True)
class ConnectionSelectionResult:
    connections: tuple[ConnectionRecord, ...]
    derived_connections: tuple[DerivedRelationship, ...] = ()
    schema_drift: frozenset[str] = frozenset()
    # See `NeighborInclusionResult.derivation_truncated` — same meaning, for the
    # derived/both-traversal connection-display search.
    derivation_truncated: bool = False


def resolve_neighbor_inclusions(
    primary_ids: frozenset[str],
    inclusions: Sequence[NeighborInclusion],
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment = EvaluationEnvironment(),
) -> NeighborInclusionResult:
    """Anchors are always the primary set — inclusions never chain off other inclusions'
    results, so this is one evaluation pass, deterministic."""
    expanded: set[str] = set()
    drift: set[str] = set()
    truncated = False
    for inclusion in inclusions:
        if inclusion.traversal == "derived":
            derived_result = _resolve_derived_inclusion(inclusion, primary_ids, read_access, registries, environment)
            expanded |= derived_result.expanded_ids
            drift |= derived_result.schema_drift
            truncated = truncated or derived_result.derivation_truncated
            continue
        for anchor_id in primary_ids:
            for connection in read_access.find_connections_for(anchor_id, direction="any"):
                if inclusion.connection_criteria is not None:
                    outcome = evaluate_connection_criteria(
                        inclusion.connection_criteria,
                        connection,
                        read_access=read_access,
                        registries=registries,
                        environment=environment,
                    )
                    drift |= outcome.schema_drift
                    if not outcome.matched:
                        continue
                if not direction_matches(connection, anchor_id, inclusion.direction, registries):
                    continue
                neighbor_id = connection.target if connection.source == anchor_id else connection.source
                if neighbor_id in primary_ids or neighbor_id in expanded:
                    continue
                neighbor_entity = read_access.get_entity(neighbor_id)
                if neighbor_entity is None:
                    continue  # dangling endpoint never matches
                if inclusion.neighbor_criteria is not None:
                    outcome = evaluate_entity_criteria(
                        inclusion.neighbor_criteria,
                        neighbor_entity,
                        read_access=read_access,
                        registries=registries,
                        environment=environment,
                    )
                    drift |= outcome.schema_drift
                    if not outcome.matched:
                        continue
                expanded.add(neighbor_id)
    return NeighborInclusionResult(frozenset(expanded), frozenset(drift), truncated)


def _resolve_derived_inclusion(
    inclusion: NeighborInclusion,
    primary_ids: frozenset[str],
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment,
) -> NeighborInclusionResult:
    if registries.derivation_catalog is None:
        return NeighborInclusionResult(frozenset())
    derived_set = derive_relationships(
        RelationshipDerivationRequest(
            primary_ids,
            inclusion.direction,
            "include_potential" if inclusion.include_potential else "certain_only",
            DerivationBounds(
                inclusion.max_hops or registries.derivation_max_hops,
                registries.derivation_max_relationships,
                registries.derivation_time_budget_seconds,
            ),
        ),
        read_access=read_access,
        registries=registries.derivation_catalog,
    )
    expanded: set[str] = set()
    drift: set[str] = set()
    for relationship in derived_set.relationships:
        neighbor_id = relationship.target_id if relationship.source_id in primary_ids else relationship.source_id
        if neighbor_id in primary_ids:
            continue
        if inclusion.connection_criteria is not None:
            from src.domain.viewpoints.viewpoint_criteria_evaluation import _derived_matches

            if not _derived_matches(
                inclusion.connection_criteria, relationship.connection_type, relationship.certainty, relationship.hops
            ):
                continue
        neighbor = read_access.get_entity(neighbor_id)
        if neighbor is None:
            continue
        if inclusion.neighbor_criteria is not None:
            outcome = evaluate_entity_criteria(
                inclusion.neighbor_criteria,
                neighbor,
                read_access=read_access,
                registries=registries,
                environment=environment,
            )
            drift |= outcome.schema_drift
            if not outcome.matched:
                continue
        expanded.add(neighbor_id)
    return NeighborInclusionResult(frozenset(expanded), frozenset(drift), derived_set.truncated)


def select_connections(
    included_entity_ids: frozenset[str],
    selection: ConnectionSelection,
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment = EvaluationEnvironment(),
) -> ConnectionSelectionResult:
    """Structural invariant: a connection is included only if both endpoints are in
    ``included_entity_ids``; ``selection.criteria`` narrows within that set and can never
    widen past it."""
    if not selection.enabled:
        return ConnectionSelectionResult(())
    return _select(
        included_entity_ids,
        selection,
        read_access=read_access,
        registries=registries,
        bridging=None,
        environment=environment,
    )


def select_matrix_connections(
    row_entity_ids: frozenset[str],
    column_entity_ids: frozenset[str],
    selection: ConnectionSelection,
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment = EvaluationEnvironment(),
) -> ConnectionSelectionResult:
    """Matrix bridging invariant: included only if one endpoint is in the row
    population and the OTHER is in the column population — row↔column only, never row↔row
    or column↔column."""
    if not selection.enabled:
        return ConnectionSelectionResult(())
    combined = row_entity_ids | column_entity_ids
    return _select(
        combined,
        selection,
        read_access=read_access,
        registries=registries,
        bridging=(row_entity_ids, column_entity_ids),
        environment=environment,
    )


def _select(
    scan_ids: frozenset[str],
    selection: ConnectionSelection,
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    bridging: tuple[frozenset[str], frozenset[str]] | None,
    environment: EvaluationEnvironment,
) -> ConnectionSelectionResult:
    seen: dict[str, ConnectionRecord] = {}
    drift: set[str] = set()
    if selection.traversal in {"direct", "both"}:
        for entity_id in scan_ids:
            for connection in read_access.find_connections_for(entity_id, direction="any"):
                if connection.artifact_id in seen:
                    continue
                if bridging is None:
                    structurally_included = connection.source in scan_ids and connection.target in scan_ids
                else:
                    rows, columns = bridging
                    structurally_included = (connection.source in rows and connection.target in columns) or (
                        connection.source in columns and connection.target in rows
                    )
                if not structurally_included:
                    continue
                outcome = evaluate_connection_criteria(
                    selection.criteria,
                    connection,
                    read_access=read_access,
                    registries=registries,
                    environment=environment,
                )
                drift |= outcome.schema_drift
                if outcome.matched:
                    seen[connection.artifact_id] = connection
    ordered = tuple(sorted(seen.values(), key=lambda connection: connection.artifact_id))
    derived, derivation_truncated = _select_derived(scan_ids, selection, read_access, registries, bridging)
    return ConnectionSelectionResult(ordered, derived, frozenset(drift), derivation_truncated)


def _select_derived(
    scan_ids: frozenset[str],
    selection: ConnectionSelection,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    bridging: tuple[frozenset[str], frozenset[str]] | None,
) -> tuple[tuple[DerivedRelationship, ...], bool]:
    if selection.traversal not in {"derived", "both"} or registries.derivation_catalog is None:
        return (), False
    derived_set = derive_relationships(
        RelationshipDerivationRequest(
            scan_ids,
            "either",
            "include_potential" if selection.include_potential else "certain_only",
            DerivationBounds(
                selection.max_hops or registries.derivation_max_hops,
                registries.derivation_max_relationships,
                registries.derivation_time_budget_seconds,
            ),
        ),
        read_access=read_access,
        registries=registries.derivation_catalog,
    )
    included: list[DerivedRelationship] = []
    for relationship in derived_set.relationships:
        if bridging is None:
            structural = relationship.source_id in scan_ids and relationship.target_id in scan_ids
        else:
            rows, columns = bridging
            structural = (relationship.source_id in rows and relationship.target_id in columns) or (
                relationship.source_id in columns and relationship.target_id in rows
            )
        if structural and _derived_matches(
            selection.criteria, relationship.connection_type, relationship.certainty, relationship.hops
        ):
            included.append(relationship)
    return tuple(sorted(included, key=lambda relationship: relationship.artifact_id)), derived_set.truncated
