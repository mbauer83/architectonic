"""Encoding-independent semantic invariants for derived relationships."""

from __future__ import annotations

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.relationships.relationship_derivation import OrientedRelation, compose
from src.ontologies.archimate_4 import module
from tests.domain.test_relationship_derivation_exhaustive import _expected_rule, _joined_pairs, _oriented_pair


def test_derived_relationships_preserve_the_specification_invariants() -> None:
    observed = 0
    for first, second, join, intermediate in _joined_pairs():
        result = compose(
            *_oriented_pair(first, second, join),
            intermediate,
            module.derivation_rules,
            module.permitted_relationships,
            module.derivation_restrictions,
        )
        if result is None:
            continue
        observed += 1
        expected = _expected_rule(first, second, join, intermediate)
        assert expected is not None
        if expected["certainty"] == "potential":
            assert result.certainty == "potential"
        if result.connection_type.artifact_type == "archimate-access":
            assert result.target_info is not None
            assert "passive-structure-element" in result.target_info.classes
        if result.connection_type.artifact_type == "archimate-influence":
            assert result.target_info is not None
            assert result.target_info.hierarchy[0] == "motivation"
        if result.source_info is not None and "junction" in result.source_info.classes:
            assert result.connection_type.artifact_type == "archimate-association"
        if first.connection_type.derivation_role == second.connection_type.derivation_role == "structural":
            assert result.connection_type.derivation_role == "structural"
            assert result.connection_type.derivation_strength is not None
            assert first.connection_type.derivation_strength is not None
            assert second.connection_type.derivation_strength is not None
            assert result.connection_type.derivation_strength <= min(
                first.connection_type.derivation_strength, second.connection_type.derivation_strength
            )
    assert observed > 1_000


def test_grouped_candidates_require_permission_only_for_their_explicit_rule() -> None:
    grouping = module.entity_types[EntityTypeName("grouping")]
    first = _relation("archimate-aggregation", "grouping", "application-component", "group", "component")
    second = _relation("archimate-realization", "grouping", "service", "group", "service")

    assert (
        compose(
            first,
            second,
            grouping,
            module.derivation_rules,
            module.permitted_relationships,
            module.derivation_restrictions,
        )
        is None
    )


def _relation(
    connection_name: str,
    source_type: str,
    target_type: str,
    source_id: str,
    target_id: str,
) -> OrientedRelation:
    return OrientedRelation(
        connection_name,
        module.connection_types[ConnectionTypeName(connection_name)],
        source_id,
        target_id,
        source_type=EntityTypeName(source_type),
        target_type=EntityTypeName(target_type),
        source_info=module.entity_types[EntityTypeName(source_type)],
        target_info=module.entity_types[EntityTypeName(target_type)],
    )
