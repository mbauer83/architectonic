"""Result-type syntax and conservative binding inference."""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_value_types import (
    BindingTypeError,
    ConnectionInstanceType,
    ConnectionSetType,
    EntityInstanceType,
    EntitySetType,
    ListType,
    OptionalType,
    QueryResultType,
    ScalarType,
    TupleType,
    assert_types_are_compatible,
    format_result_type,
    infer_binding_type,
    parse_result_type,
    types_are_compatible,
)

_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component", "process"}),
    known_connection_types=frozenset(),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={"cost": "number", "start": "date"},
    connection_attribute_types={},
)


@pytest.mark.parametrize(
    "value",
    [
        EntityInstanceType(frozenset({"process"})),
        ConnectionInstanceType(frozenset({"assignment"})),
        EntitySetType(frozenset({"application-component", "process"})),
        ConnectionSetType(frozenset({"assignment", "serving"})),
        OptionalType(EntityInstanceType(frozenset({"process"}))),
        ListType(ScalarType("number")),
        TupleType((EntityInstanceType(frozenset({"process"})), ScalarType("date"))),
    ],
)
def test_result_type_syntax_round_trips(value: QueryResultType) -> None:
    assert parse_result_type(format_result_type(value)) == value


def test_selection_inference_is_conservative_and_checks_declared_unions() -> None:
    criteria = EntityCriteriaGroup(children=(AttributeCondition("type", "in", ValueRef(literal=["process"])),))
    inferred = infer_binding_type(select="entities", criteria=criteria, registries=_REGISTRIES)

    assert inferred == EntitySetType(frozenset({"process"}))
    assert types_are_compatible(EntityInstanceType(frozenset({"process"})), inferred)
    assert types_are_compatible(OptionalType(EntityInstanceType(frozenset({"process"}))), OptionalType(inferred))
    assert not types_are_compatible(EntitySetType(frozenset({"application-component"})), inferred)


def test_projection_preserves_cardinality_and_rejects_open_schema_attributes() -> None:
    values = infer_binding_type(
        select="entities",
        criteria=EntityCriteriaGroup(children=(AttributeCondition("type", "eq", ValueRef(literal="process")),)),
        project="cost",
        registries=_REGISTRIES,
    )
    optional = infer_binding_type(
        input_type=OptionalType(EntityInstanceType(frozenset({"process"}))), project="cost", registries=_REGISTRIES
    )

    singleton = infer_binding_type(
        input_type=EntityInstanceType(frozenset({"process"})), project="cost", registries=_REGISTRIES
    )

    assert values == ListType(ScalarType("number"))
    assert singleton == ScalarType("number")
    assert optional == OptionalType(ScalarType("number"))
    with pytest.raises(BindingTypeError) as error:
        infer_binding_type(select="entities", project="cost", registries=_REGISTRIES)
    assert error.value.code == "binding-attribute-type-ambiguous"
    assert infer_binding_type(select="entities", project="name", registries=_REGISTRIES) == ListType(
        ScalarType("string")
    )


def test_aggregate_kinds_and_instance_rejection_are_pinned() -> None:
    criteria = EntityCriteriaGroup(children=(AttributeCondition("type", "eq", ValueRef(literal="process")),))
    values = infer_binding_type(select="entities", project="cost", criteria=criteria, registries=_REGISTRIES)

    assert infer_binding_type(
        select="entities", project="cost", aggregate="avg", criteria=criteria, registries=_REGISTRIES
    ) == ScalarType("number")
    assert infer_binding_type(
        select="entities", project="start", aggregate="min", criteria=criteria, registries=_REGISTRIES
    ) == ScalarType("date")
    assert values == ListType(ScalarType("number"))
    assert infer_binding_type(
        select="entities", criteria=criteria, aggregate="count", registries=_REGISTRIES
    ) == ScalarType("integer")
    assert infer_binding_type(
        select="entities", project="cost", aggregate="sum", criteria=criteria, registries=_REGISTRIES
    ) == ScalarType("number")
    assert infer_binding_type(
        select="entities", project="start", aggregate="max", criteria=criteria, registries=_REGISTRIES
    ) == ScalarType("date")
    with pytest.raises(BindingTypeError) as error:
        infer_binding_type(
            input_type=EntityInstanceType(frozenset({"process"})), aggregate="count", registries=_REGISTRIES
        )
    assert error.value.code == "aggregate-over-instance"
    with pytest.raises(BindingTypeError) as error:
        infer_binding_type(input_type=ListType(ScalarType("date")), aggregate="sum", registries=_REGISTRIES)
    assert error.value.code == "aggregate-type-mismatch"


def test_tuple_compatibility_requires_matching_arity_and_element_types() -> None:
    declared = TupleType((ScalarType("number"), ScalarType("date")))

    assert types_are_compatible(declared, declared)
    with pytest.raises(BindingTypeError) as error:
        assert_types_are_compatible(declared, TupleType((ScalarType("number"),)))
    assert error.value.code == "tuple-arity-mismatch"


def test_nested_tuple_and_list_syntax_preserve_fixed_arity() -> None:
    value = parse_result_type("tuple[entity[process], list[number], optional[connection[assignment]]]")

    assert value == TupleType(
        (
            EntityInstanceType(frozenset({"process"})),
            ListType(ScalarType("number")),
            OptionalType(ConnectionInstanceType(frozenset({"assignment"}))),
        )
    )
    assert format_result_type(value) == "tuple[entity[process], list[number], optional[connection[assignment]]]"
