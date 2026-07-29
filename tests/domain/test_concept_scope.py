"""Tests for ConceptScope predicates and intersections."""

from __future__ import annotations

from src.domain.concept_scope import ConceptScope, EndpointRule, HierarchyPredicate
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_types import EntityTypeInfo


def _entity_info(artifact_type: str, hierarchy: tuple[str, ...], classes: tuple[str, ...] = ()) -> EntityTypeInfo:
    return EntityTypeInfo(
        artifact_type=artifact_type,
        prefix=artifact_type[:3].upper(),
        hierarchy=hierarchy,
        classes=classes,
        create_when="",
        never_create_when="",
    )


def test_unrestricted_scope_admits_any_type() -> None:
    scope = ConceptScope.unrestricted()

    assert scope.admits_entity_type(EntityTypeName("service")) is True
    assert scope.admits_connection_type(ConnectionTypeName("archimate-serving")) is True
    assert scope.admits_connection(
        EntityTypeName("service"),
        EntityTypeName("role"),
        ConnectionTypeName("archimate-serving"),
    )


def test_entity_scope_combines_explicit_class_and_hierarchy_predicates() -> None:
    service = _entity_info("service", ("business", "service"), ("behavior", "external"))
    process = _entity_info("process", ("business", "process"), ("behavior",))
    technology_service = _entity_info("service", ("technology", "service"), ("behavior", "external"))
    scope = ConceptScope(
        entity_types=frozenset({EntityTypeName("service"), EntityTypeName("process")}),
        entity_class_predicates=(frozenset({"external"}),),
        hierarchy_predicates=(HierarchyPredicate(index=0, values=frozenset({"business"})),),
    )

    assert scope.admits_entity_type(EntityTypeName("service"), service) is True
    assert scope.admits_entity_type(EntityTypeName("process"), process) is False
    assert scope.admits_entity_type(EntityTypeName("service"), technology_service) is False
    assert scope.admits_entity_type(EntityTypeName("unknown"), service) is False
    assert scope.admits_entity_type(EntityTypeName("service")) is False


def test_connection_scope_applies_endpoint_rules_when_present() -> None:
    scope = ConceptScope(
        connection_types=frozenset({ConnectionTypeName("archimate-flow")}),
        endpoint_rules=(
            EndpointRule(
                connection_type=ConnectionTypeName("archimate-flow"),
                source_types=frozenset({EntityTypeName("business-actor")}),
                target_types=frozenset({EntityTypeName("role")}),
            ),
        ),
    )

    assert scope.admits_connection_type(ConnectionTypeName("archimate-flow")) is True
    assert scope.admits_connection_type(ConnectionTypeName("archimate-serving")) is False
    assert scope.admits_connection(
        EntityTypeName("business-actor"),
        EntityTypeName("role"),
        ConnectionTypeName("archimate-flow"),
    )
    assert not scope.admits_connection(
        EntityTypeName("role"),
        EntityTypeName("business-actor"),
        ConnectionTypeName("archimate-flow"),
    )


def test_intersection_combines_type_sets_and_predicates() -> None:
    left = ConceptScope(
        entity_types=frozenset({EntityTypeName("service"), EntityTypeName("process"), EntityTypeName("role")}),
        hierarchy_predicates=(HierarchyPredicate(index=0, values=frozenset({"business", "application"})),),
        connection_types=frozenset({ConnectionTypeName("archimate-flow"), ConnectionTypeName("archimate-serving")}),
        endpoint_rules=(
            EndpointRule(
                connection_type=ConnectionTypeName("archimate-flow"),
                source_types=frozenset({EntityTypeName("service"), EntityTypeName("process")}),
            ),
        ),
    )
    right = ConceptScope(
        entity_types=frozenset({EntityTypeName("service"), EntityTypeName("role")}),
        hierarchy_predicates=(HierarchyPredicate(index=0, values=frozenset({"business"})),),
        connection_types=frozenset({ConnectionTypeName("archimate-flow")}),
        endpoint_rules=(
            EndpointRule(
                connection_type=ConnectionTypeName("archimate-flow"),
                source_types=frozenset({EntityTypeName("service")}),
                target_types=frozenset({EntityTypeName("role")}),
            ),
        ),
    )

    scope = left & right
    service = _entity_info("service", ("business", "service"), ("behavior",))

    assert scope.entity_types == frozenset({EntityTypeName("service"), EntityTypeName("role")})
    assert scope.hierarchy_predicates == (HierarchyPredicate(index=0, values=frozenset({"business"})),)
    assert scope.connection_types == frozenset({ConnectionTypeName("archimate-flow")})
    assert scope.admits_entity_type(EntityTypeName("service"), service)
    assert scope.admits_connection(
        EntityTypeName("service"),
        EntityTypeName("role"),
        ConnectionTypeName("archimate-flow"),
    )
    assert not scope.admits_connection(
        EntityTypeName("process"),
        EntityTypeName("role"),
        ConnectionTypeName("archimate-flow"),
    )


def test_excluded_entity_types_carve_an_exception_out_of_unrestricted_scope() -> None:
    scope = ConceptScope(excluded_entity_types=frozenset({EntityTypeName("assessment")}))

    assert scope.admits_entity_type(EntityTypeName("goal")) is True
    assert scope.admits_entity_type(EntityTypeName("assessment")) is False


def test_excluded_hierarchy_predicate_excludes_a_whole_domain_including_future_types() -> None:
    scope = ConceptScope(excluded_hierarchy_predicates=(HierarchyPredicate(index=0, values=frozenset({"assurance"})),))
    existing_assurance_type = _entity_info("risk", ("assurance", "risk"))
    a_new_assurance_type_added_later = _entity_info("control", ("assurance", "control"))
    unrelated_type = _entity_info("goal", ("motivation", "goal"))

    assert scope.admits_entity_type(EntityTypeName("risk"), existing_assurance_type) is False
    assert scope.admits_entity_type(EntityTypeName("control"), a_new_assurance_type_added_later) is False
    assert scope.admits_entity_type(EntityTypeName("goal"), unrelated_type) is True


def test_exclusion_overrides_an_explicit_allow_list_entry() -> None:
    scope = ConceptScope(
        entity_types=frozenset({EntityTypeName("goal"), EntityTypeName("assessment")}),
        excluded_entity_types=frozenset({EntityTypeName("assessment")}),
    )

    assert scope.admits_entity_type(EntityTypeName("goal")) is True
    assert scope.admits_entity_type(EntityTypeName("assessment")) is False


def test_excluded_connection_types_carve_an_exception_out_of_unrestricted_scope() -> None:
    scope = ConceptScope(excluded_connection_types=frozenset({ConnectionTypeName("archimate-association")}))

    assert scope.admits_connection_type(ConnectionTypeName("archimate-serving")) is True
    assert scope.admits_connection_type(ConnectionTypeName("archimate-association")) is False


def test_excluded_entity_type_blocks_a_connection_through_that_endpoint() -> None:
    scope = ConceptScope(excluded_entity_types=frozenset({EntityTypeName("role")}))

    assert not scope.admits_connection(
        EntityTypeName("service"), EntityTypeName("role"), ConnectionTypeName("archimate-serving")
    )
    assert scope.admits_connection(
        EntityTypeName("service"), EntityTypeName("process"), ConnectionTypeName("archimate-serving")
    )


def test_intersection_unions_exclusions_from_both_sides() -> None:
    left = ConceptScope(excluded_entity_types=frozenset({EntityTypeName("assessment")}))
    right = ConceptScope(excluded_entity_types=frozenset({EntityTypeName("driver")}))

    scope = left & right

    assert scope.excluded_entity_types == frozenset({EntityTypeName("assessment"), EntityTypeName("driver")})
    assert scope.admits_entity_type(EntityTypeName("assessment")) is False
    assert scope.admits_entity_type(EntityTypeName("driver")) is False
    assert scope.admits_entity_type(EntityTypeName("goal")) is True


def test_intersection_unions_excluded_hierarchy_predicates_from_both_sides() -> None:
    left = ConceptScope(excluded_hierarchy_predicates=(HierarchyPredicate(index=0, values=frozenset({"assurance"})),))
    right = ConceptScope(excluded_hierarchy_predicates=(HierarchyPredicate(index=0, values=frozenset({"legacy"})),))
    assurance_type = _entity_info("risk", ("assurance", "risk"))
    legacy_type = _entity_info("archived", ("legacy", "archived"))
    unrelated_type = _entity_info("goal", ("motivation", "goal"))

    scope = left & right

    assert scope.admits_entity_type(EntityTypeName("risk"), assurance_type) is False
    assert scope.admits_entity_type(EntityTypeName("archived"), legacy_type) is False
    assert scope.admits_entity_type(EntityTypeName("goal"), unrelated_type) is True
