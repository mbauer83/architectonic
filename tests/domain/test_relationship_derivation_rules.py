"""Certain relationship-composition behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest

from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.relationship_derivation import OrientedRelation, compose, fold_chain
from src.domain.relationships.relationship_derivation_rules import load_composition_rules
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, load_archimate_4_module


def _connection(
    name: str,
    role: Literal["structural", "dependency", "dynamic", "specialization"],
    strength: int | None = None,
) -> ConnectionTypeInfo:
    return ConnectionTypeInfo(
        artifact_type=name, conn_lang="archimate", derivation_role=role, derivation_strength=strength
    )


def _relation(
    name: str,
    role: Literal["structural", "dependency", "dynamic", "specialization"],
    source: str,
    target: str,
    strength: int | None = None,
    reverse: bool = False,
) -> OrientedRelation:
    return OrientedRelation(
        name, _connection(name, role, strength), source, target, "reverse" if reverse else "forward"
    )


_CORE = EntityTypeInfo("component", "APP", ("application",), (), "", "")
_RULES = load_archimate_4_module(_PACKAGE_DIR).derivation_rules


def test_ontology_can_supply_composition_rules_from_its_own_yaml(tmp_path: Path) -> None:
    rules_path = tmp_path / "relationship_derivation.yaml"
    rules_path.write_text(
        "composition_rules:\n"
        "  - {spec_ref: EX-1, certainty: certain, first_role: structural, second_role: dependency, result: second}\n",
        encoding="utf-8",
    )

    rules = load_composition_rules(tmp_path)

    assert len(rules) == 1
    assert rules[0].spec_ref == "EX-1"


@pytest.mark.parametrize(
    ("first", "second", "expected_type", "expected_endpoints"),
    [
        (
            _relation("archimate-specialization", "specialization", "a", "b"),
            _relation("archimate-specialization", "specialization", "b", "c"),
            "archimate-specialization",
            ("a", "c"),
        ),
        (
            _relation("archimate-composition", "structural", "a", "b", 4),
            _relation("archimate-realization", "structural", "b", "c", 1),
            "archimate-realization",
            ("a", "c"),
        ),
        (
            _relation("archimate-assignment", "structural", "a", "b", 2),
            _relation("archimate-serving", "dependency", "b", "c", 4),
            "archimate-serving",
            ("a", "c"),
        ),
        (
            _relation("archimate-assignment", "structural", "a", "b", 2),
            _relation("archimate-serving", "dependency", "b", "c", 4, True),
            "archimate-serving",
            ("c", "a"),
        ),
        (
            _relation("archimate-aggregation", "structural", "a", "b", 3),
            _relation("archimate-flow", "dynamic", "b", "c"),
            "archimate-flow",
            ("a", "c"),
        ),
        (
            _relation("archimate-aggregation", "structural", "a", "b", 3),
            _relation("archimate-flow", "dynamic", "b", "c", None, True),
            "archimate-flow",
            ("c", "a"),
        ),
        (
            _relation("archimate-triggering", "dynamic", "a", "b"),
            _relation("archimate-assignment", "structural", "b", "c", 2),
            "archimate-triggering",
            ("a", "c"),
        ),
        (
            _relation("archimate-triggering", "dynamic", "a", "b"),
            _relation("archimate-triggering", "dynamic", "b", "c"),
            "archimate-triggering",
            ("a", "c"),
        ),
    ],
    ids=["spec-dr1", "spec-dr2", "spec-dr3", "spec-dr4", "spec-dr5", "spec-dr6", "spec-dr7", "spec-dr8"],
)
def test_joined_relationships_derive_the_expected_certain_type(
    first: OrientedRelation,
    second: OrientedRelation,
    expected_type: str,
    expected_endpoints: tuple[str, str],
) -> None:
    derived = compose(first, second, _CORE, _RULES)

    assert derived is not None
    assert derived.connection_type.artifact_type == expected_type
    assert (derived.source_id, derived.target_id) == expected_endpoints
    assert derived.certainty == "certain"


def test_structural_chain_derives_the_weakest_relationship() -> None:
    relations = (
        _relation("archimate-composition", "structural", "a", "b", 4),
        _relation("archimate-assignment", "structural", "b", "c", 2),
        _relation("archimate-realization", "structural", "c", "d", 1),
    )

    derived = fold_chain(relations, (_CORE, _CORE), _RULES)

    assert derived is not None
    assert derived.connection_type.artifact_type == "archimate-realization"
    assert (derived.source_id, derived.target_id) == ("a", "d")


def test_junction_and_self_loop_do_not_produce_a_derived_relationship() -> None:
    first = _relation("archimate-assignment", "structural", "a", "b", 2)
    second = _relation("archimate-serving", "dependency", "b", "a", 4)
    junction = EntityTypeInfo("and-junction", "JNC", ("common",), ("junction",), "", "")

    assert compose(first, second, _CORE, _RULES) is None
    assert compose(first, _relation("archimate-serving", "dependency", "b", "c", 4), junction, _RULES) is None
