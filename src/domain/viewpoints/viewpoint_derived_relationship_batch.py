"""Batched relationship-derived attribute evaluation: every entity needing a given
`traversal: derived` attribute is folded into one `derive_relationships` call over their
combined anchor set, instead of one call per entity.

`derive_relationships` already treats its `anchors` parameter as a set representing shared
reachability — `resolve_neighbor_inclusions` has relied on this for a multi-entity primary
population since it shipped. Each resulting relationship is attributed by its own recorded
`source_id`/`target_id`, so folding many entities into one combined anchor set produces,
for each entity, exactly the relationships a solo single-anchor call for that entity alone
would have — the BFS discovers every anchor's own local neighborhood at hop 0 before any
anchor's deeper frontier is explored, so no anchor's own directly-reachable relationships
are ever shadowed by another anchor's traversal. Composing the fold once and re-attributing
by endpoint is what keeps this at the plan's stated bounded-reachability complexity per
execution, rather than multiplying it by the number of entities being evaluated.
"""

from __future__ import annotations

from src.domain.relationships.relationship_reachability import (
    DerivationBounds,
    DerivedRelationship,
    RelationshipDerivationRequest,
    derive_relationships,
)
from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute
from src.domain.viewpoints.viewpoint_condition_evaluation import read_attribute_value
from src.domain.viewpoints.viewpoint_criteria import IncidentDirection
from src.domain.viewpoints.viewpoint_criteria_evaluation import _derived_matches, evaluate_entity_criteria
from src.domain.viewpoints.viewpoint_derived_value_reduction import reduce_values
from src.domain.viewpoints.viewpoint_evaluation_context import BindingEvaluationInput, EvaluationEnvironment


def _incident_pairs(
    relationship: DerivedRelationship, anchors: frozenset[str], direction: IncidentDirection
) -> list[tuple[str, str]]:
    """`(anchor_entity_id, other_entity_id)` for every anchor this relationship is
    incident to from its own perspective — a relationship between two anchors is incident
    to both, exactly as it would be if each anchor had been queried on its own."""
    pairs: list[tuple[str, str]] = []
    if direction in ("outgoing", "either") and relationship.source_id in anchors:
        pairs.append((relationship.source_id, relationship.target_id))
    if direction in ("incoming", "either") and relationship.target_id in anchors:
        pairs.append((relationship.target_id, relationship.source_id))
    return pairs


def evaluate_relationship_derived_batch(
    attribute: DerivedAttribute,
    entity_ids: tuple[str, ...],
    input: BindingEvaluationInput,
    environment: EvaluationEnvironment,
) -> dict[str, object]:
    """One `derived.<name>` value per entity in `entity_ids`, computed from a single
    combined relationship derivation rather than one derivation per entity."""
    catalog = input.registries.derivation_catalog
    if catalog is None or not entity_ids:
        return dict.fromkeys(entity_ids, 0 if attribute.reduce == "count" else None)

    anchors = frozenset(entity_ids)
    relationships = derive_relationships(
        RelationshipDerivationRequest(
            anchors,
            attribute.direction,
            "include_potential" if attribute.include_potential else "certain_only",
            DerivationBounds(
                attribute.max_hops or input.registries.derivation_max_hops,
                input.registries.derivation_max_relationships,
                input.registries.derivation_time_budget_seconds,
            ),
        ),
        read_access=input.read_access,
        registries=catalog,
    ).relationships

    counts: dict[str, int] = dict.fromkeys(entity_ids, 0)
    collected: dict[str, list[object]] = {entity_id: [] for entity_id in entity_ids}
    for relationship in relationships:
        if attribute.connection_criteria is not None and not _derived_matches(
            attribute.connection_criteria, relationship.connection_type, relationship.certainty, relationship.hops
        ):
            continue
        for entity_id, other_id in _incident_pairs(relationship, anchors, attribute.direction):
            endpoint = input.read_access.get_entity(other_id)
            if endpoint is None:
                continue
            if (
                attribute.endpoint_criteria is not None
                and not evaluate_entity_criteria(
                    attribute.endpoint_criteria,
                    endpoint,
                    read_access=input.read_access,
                    registries=input.registries,
                    environment=environment,
                ).matched
            ):
                continue
            counts[entity_id] += 1
            if attribute.of == "relationship.hops":
                collected[entity_id].append(relationship.hops)
            elif attribute.of is not None and attribute.of.startswith("endpoint."):
                value, present = read_attribute_value(
                    endpoint, attribute.of.removeprefix("endpoint."), context="entity", environment=environment
                )
                if present:
                    collected[entity_id].append(value)

    if attribute.reduce == "count":
        return dict(counts)
    return {entity_id: reduce_values(tuple(collected[entity_id]), attribute.reduce) for entity_id in entity_ids}
