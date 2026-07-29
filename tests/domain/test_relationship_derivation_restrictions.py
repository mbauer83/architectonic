"""Admissibility behavior for derived relationships."""

from __future__ import annotations

import pytest

from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.relationship_derivation import OrientedRelation, compose
from src.domain.relationships.relationship_derivation_restrictions import (
    DerivationRestriction,
    permits_derived_relationship,
)
from src.ontologies.archimate_4._loader import _PACKAGE_DIR, load_archimate_4_module


def _entity(name: str, domain: str, *, passive: bool = False) -> EntityTypeInfo:
    classes = ("passive-structure-element",) if passive else (("junction",) if name == "junction" else ())
    return EntityTypeInfo(name, name[:3].upper(), (domain,), classes, "", "")


def _connection(name: str) -> ConnectionTypeInfo:
    return ConnectionTypeInfo(name, "archimate")


@pytest.mark.parametrize(
    ("rule", "source", "target", "connection", "intermediate", "allowed_type", "blocked_type"),
    [
        (
            DerivationRestriction(
                "R1",
                frozenset({"core"}),
                frozenset({"motivation"}),
                allowed_connection_artifact_types=frozenset({"archimate-assignment"}),
            ),
            _entity("app", "application"),
            _entity("goal", "motivation"),
            _connection("archimate-assignment"),
            _entity("step", "application"),
            "archimate-assignment",
            "archimate-triggering",
        ),
        (
            DerivationRestriction(
                "R2",
                frozenset({"motivation"}),
                frozenset({"core"}),
                allowed_connection_artifact_types=frozenset({"archimate-association"}),
            ),
            _entity("goal", "motivation"),
            _entity("app", "application"),
            _connection("archimate-association"),
            _entity("step", "motivation"),
            "archimate-association",
            "archimate-assignment",
        ),
        (
            DerivationRestriction(
                "R3",
                frozenset({"core"}),
                frozenset({"strategy"}),
                allowed_connection_artifact_types=frozenset({"archimate-realization"}),
            ),
            _entity("app", "application"),
            _entity("capability", "strategy"),
            _connection("archimate-realization"),
            _entity("step", "application"),
            "archimate-realization",
            "archimate-assignment",
        ),
        (
            DerivationRestriction(
                "R4",
                frozenset({"strategy"}),
                frozenset({"core"}),
                allowed_connection_artifact_types=frozenset({"archimate-association"}),
            ),
            _entity("capability", "strategy"),
            _entity("app", "application"),
            _connection("archimate-association"),
            _entity("step", "strategy"),
            "archimate-association",
            "archimate-serving",
        ),
        (
            DerivationRestriction(
                "R5",
                frozenset({"implementation_migration"}),
                frozenset({"core"}),
                allowed_connection_artifact_types=frozenset({"archimate-realization"}),
            ),
            _entity("plateau", "implementation"),
            _entity("app", "application"),
            _connection("archimate-realization"),
            _entity("step", "implementation"),
            "archimate-realization",
            "archimate-serving",
        ),
        (
            DerivationRestriction(
                "R6",
                frozenset({"core"}),
                frozenset({"implementation_migration"}),
                allowed_connection_artifact_types=frozenset({"archimate-assignment"}),
            ),
            _entity("app", "application"),
            _entity("plateau", "implementation"),
            _connection("archimate-assignment"),
            _entity("step", "application"),
            "archimate-assignment",
            "archimate-serving",
        ),
        (
            DerivationRestriction(
                "R7",
                source_artifact_types=frozenset({"grouping"}),
                target_domains=frozenset({"relationships"}),
                allowed_connection_artifact_types=frozenset({"archimate-aggregation"}),
            ),
            _entity("grouping", "common"),
            _entity("junction", "common"),
            _connection("archimate-aggregation"),
            _entity("step", "common"),
            "archimate-aggregation",
            "archimate-serving",
        ),
        (
            DerivationRestriction(
                "R8",
                source_artifact_types_excluded=frozenset({"grouping"}),
                target_domains=frozenset({"relationships"}),
                allowed_connection_artifact_types=frozenset({"archimate-association"}),
            ),
            _entity("app", "application"),
            _entity("junction", "common"),
            _connection("archimate-association"),
            _entity("step", "application"),
            "archimate-association",
            "archimate-serving",
        ),
        (
            DerivationRestriction(
                "R9",
                source_domains=frozenset({"relationships"}),
                allowed_connection_artifact_types=frozenset({"archimate-association"}),
            ),
            _entity("junction", "common"),
            _entity("app", "application"),
            _connection("archimate-association"),
            _entity("step", "common"),
            "archimate-association",
            "archimate-serving",
        ),
        (
            DerivationRestriction(
                "R10",
                target_domains_excluded=frozenset({"motivation"}),
                connection_artifact_types=frozenset({"archimate-influence"}),
                always_disallow=True,
            ),
            _entity("app", "application"),
            _entity("app2", "application"),
            _connection("archimate-influence"),
            _entity("step", "application"),
            "archimate-association",
            "archimate-influence",
        ),
        (
            DerivationRestriction(
                "R11",
                target_passive=False,
                connection_artifact_types=frozenset({"archimate-access"}),
                always_disallow=True,
            ),
            _entity("app", "application"),
            _entity("app2", "application"),
            _connection("archimate-access"),
            _entity("step", "application"),
            "archimate-association",
            "archimate-access",
        ),
        (
            DerivationRestriction(
                "R12",
                source_passive=False,
                target_passive=True,
                allowed_connection_artifact_types=frozenset({"archimate-access"}),
            ),
            _entity("app", "application"),
            _entity("data", "application", passive=True),
            _connection("archimate-access"),
            _entity("step", "application"),
            "archimate-access",
            "archimate-serving",
        ),
        (
            DerivationRestriction(
                "R13",
                source_passive=True,
                target_passive=True,
                allowed_connection_artifact_types=frozenset({"archimate-realization"}),
            ),
            _entity("data1", "application", passive=True),
            _entity("data2", "application", passive=True),
            _connection("archimate-realization"),
            _entity("step", "application"),
            "archimate-realization",
            "archimate-serving",
        ),
        (
            DerivationRestriction(
                "R14",
                source_passive=True,
                target_passive=False,
                allowed_connection_artifact_types=frozenset({"archimate-influence"}),
            ),
            _entity("data", "application", passive=True),
            _entity("goal", "motivation"),
            _connection("archimate-influence"),
            _entity("step", "application"),
            "archimate-influence",
            "archimate-serving",
        ),
    ],
    ids=["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10", "r11", "r12", "r13", "r14"],
)
def test_endpoint_restrictions_allow_only_the_listed_relationship_types(
    rule: DerivationRestriction,
    source: EntityTypeInfo,
    target: EntityTypeInfo,
    connection: ConnectionTypeInfo,
    intermediate: EntityTypeInfo,
    allowed_type: str,
    blocked_type: str,
) -> None:
    assert permits_derived_relationship(source, target, _connection(allowed_type), intermediate, (rule,))
    assert not permits_derived_relationship(source, target, _connection(blocked_type), intermediate, (rule,))


def test_intermediate_domain_restriction_has_its_documented_exception() -> None:
    rule = DerivationRestriction(
        "RJ1", intermediate_domain_must_match_endpoint=True, intermediate_domain_exception=True
    )
    source = _entity("plateau", "implementation")
    target = _entity("goal", "motivation")

    assert permits_derived_relationship(
        source, target, _connection("archimate-association"), _entity("app", "application"), (rule,)
    )
    assert not permits_derived_relationship(
        source, target, _connection("archimate-association"), _entity("other", "strategy"), (rule,)
    )


def test_implementation_to_motivation_cannot_join_at_a_grouping_or_location() -> None:
    rule = DerivationRestriction(
        "RJ2",
        source_domains=frozenset({"implementation_migration"}),
        target_domains=frozenset({"motivation", "strategy"}),
        intermediate_artifact_types=frozenset({"grouping", "location"}),
        always_disallow=True,
    )

    assert not permits_derived_relationship(
        _entity("plateau", "implementation"),
        _entity("goal", "motivation"),
        _connection("archimate-association"),
        _entity("grouping", "common"),
        (rule,),
    )
    assert permits_derived_relationship(
        _entity("plateau", "implementation"),
        _entity("goal", "motivation"),
        _connection("archimate-association"),
        _entity("app", "application"),
        (rule,),
    )


def test_composition_applies_the_ontology_restrictions_as_a_final_filter() -> None:
    module = load_archimate_4_module(_PACKAGE_DIR)
    source = _entity("app", "application")
    target = _entity("goal", "motivation")
    intermediate = _entity("process", "application")
    first = OrientedRelation(
        "p",
        ConnectionTypeInfo("archimate-assignment", "archimate", derivation_role="structural", derivation_strength=2),
        "a",
        "b",
        source_info=source,
        target_info=intermediate,
    )
    second = OrientedRelation(
        "q",
        ConnectionTypeInfo("archimate-triggering", "archimate", derivation_role="dynamic"),
        "b",
        "c",
        source_info=intermediate,
        target_info=target,
    )

    assert {rule.spec_ref for rule in module.derivation_restrictions} == {
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
        "R7",
        "R8",
        "R9",
        "R10",
        "R11",
        "R12",
        "R13",
        "R14",
        "RJ1",
        "RJ2",
    }
    assert (
        compose(first, second, intermediate, module.derivation_rules, restrictions=module.derivation_restrictions)
        is None
    )
