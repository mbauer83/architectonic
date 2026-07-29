"""Potential relationship composition behavior."""

from __future__ import annotations

from typing import Literal

import pytest

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationship, PermittedRelationshipSet
from src.domain.relationships.relationship_derivation import OrientedRelation, compose, fold_chain
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, load_archimate_4_module

_RULES = load_archimate_4_module(_PACKAGE_DIR).derivation_rules
_CORE = EntityTypeInfo("component", "APP", ("application",), (), "", "")


def _relation(
    name: str,
    role: Literal["structural", "dependency", "dynamic", "specialization"],
    source: str,
    target: str,
    strength: int | None = None,
) -> OrientedRelation:
    return OrientedRelation(
        name, ConnectionTypeInfo(name, "archimate", derivation_role=role, derivation_strength=strength), source, target
    )


@pytest.mark.parametrize(
    ("first", "second", "expected_type", "expected_endpoints"),
    [
        (
            _relation("archimate-specialization", "specialization", "a", "b"),
            _relation("archimate-assignment", "structural", "b", "c", 2),
            "archimate-assignment",
            ("a", "c"),
        ),
        (
            _relation("archimate-specialization", "specialization", "a", "b"),
            _relation("archimate-serving", "dependency", "c", "b", 4),
            "archimate-serving",
            ("c", "a"),
        ),
        (
            _relation("archimate-specialization", "specialization", "a", "b"),
            _relation("archimate-flow", "dynamic", "a", "c"),
            "archimate-flow",
            ("b", "c"),
        ),
        (
            _relation("archimate-specialization", "specialization", "a", "b"),
            _relation("archimate-flow", "dynamic", "c", "a"),
            "archimate-flow",
            ("c", "b"),
        ),
        (
            _relation("archimate-aggregation", "structural", "a", "b", 3),
            _relation("archimate-serving", "dependency", "c", "a", 4),
            "archimate-serving",
            ("c", "b"),
        ),
        (
            _relation("archimate-aggregation", "structural", "a", "b", 3),
            _relation("archimate-serving", "dependency", "a", "c", 4),
            "archimate-serving",
            ("b", "c"),
        ),
        (
            _relation("archimate-serving", "dependency", "a", "b", 4),
            _relation("archimate-association", "dependency", "b", "c", 1),
            "archimate-association",
            ("a", "c"),
        ),
        (
            _relation("archimate-flow", "dynamic", "a", "b"),
            _relation("archimate-assignment", "structural", "b", "c", 2),
            "archimate-flow",
            ("a", "c"),
        ),
        (
            _relation("archimate-aggregation", "structural", "a", "b", 3),
            _relation("archimate-flow", "dynamic", "a", "c"),
            "archimate-flow",
            ("b", "c"),
        ),
        (
            _relation("archimate-flow", "dynamic", "a", "b"),
            _relation("archimate-flow", "dynamic", "b", "c"),
            "archimate-flow",
            ("a", "c"),
        ),
        (
            _relation("archimate-triggering", "dynamic", "a", "b"),
            _relation("archimate-assignment", "structural", "c", "b", 2),
            "archimate-triggering",
            ("a", "c"),
        ),
    ],
    ids=["pdr1", "pdr2", "pdr3", "pdr4", "pdr5", "pdr6", "pdr7", "pdr8", "pdr9", "pdr10", "pdr11"],
)
def test_potential_composition_preserves_the_specified_relationship(
    first: OrientedRelation,
    second: OrientedRelation,
    expected_type: str,
    expected_endpoints: tuple[str, str],
) -> None:
    derived = compose(first, second, _CORE, _RULES)

    assert derived is not None
    assert derived.certainty == "potential"
    assert derived.potential_steps == 1
    assert derived.connection_type.artifact_type == expected_type
    assert (derived.source_id, derived.target_id) == expected_endpoints


def test_grouped_aggregation_requires_a_permitted_result() -> None:
    grouping = EntityTypeInfo("grouping", "GRP", ("common",), (), "", "")
    grouped = EntityTypeName("grouped")
    target = EntityTypeName("target")
    first = OrientedRelation(
        "p",
        ConnectionTypeInfo("archimate-aggregation", "archimate", derivation_role="structural", derivation_strength=3),
        "group",
        "a",
        source_type=EntityTypeName("grouping"),
        target_type=grouped,
    )
    second = OrientedRelation(
        "q",
        ConnectionTypeInfo("archimate-assignment", "archimate", derivation_role="structural", derivation_strength=2),
        "group",
        "c",
        source_type=EntityTypeName("grouping"),
        target_type=target,
    )
    permitted = PermittedRelationshipSet(
        frozenset({PermittedRelationship(grouped, target, ConnectionTypeName("archimate-assignment"))})
    )

    assert compose(first, second, grouping, _RULES, permitted) is not None
    assert compose(first, second, grouping, _RULES, PermittedRelationshipSet.empty()) is None


def test_chain_remains_potential_after_a_certain_following_step() -> None:
    derived = fold_chain(
        (
            _relation("archimate-specialization", "specialization", "a", "b"),
            _relation("archimate-assignment", "structural", "b", "c", 2),
            _relation("archimate-realization", "structural", "c", "d", 1),
        ),
        (_CORE, _CORE),
        _RULES,
    )

    assert derived is not None
    assert derived.certainty == "potential"
    assert derived.potential_steps == 1
    assert derived.connection_type.artifact_type == "archimate-realization"
