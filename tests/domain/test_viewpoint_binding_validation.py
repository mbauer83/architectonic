"""Validation coverage for typed query declarations."""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute, QueryBinding, QueryParameter
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_validation import validate_viewpoint_definition
from src.domain.viewpoints.viewpoint_value_types import EntitySetType, ScalarType, TupleType
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, PresentationSpec, StyleRule, ViewpointDefinition


def _definition(**parts: object) -> ViewpointDefinition:
    return ViewpointDefinition(
        slug="typed-query",
        version=1,
        name="Typed query",
        query=ExecutableViewpointQuery(**parts),
    )


def _issues(definition: ViewpointDefinition, **limits: object) -> tuple[object, ...]:
    return validate_viewpoint_definition(
        definition,
        mode="save",
        known_entity_types=frozenset({"requirement"}),
        known_connection_types=frozenset({"archimate-serving"}),
        known_specialization_slugs=frozenset(),
        entity_attribute_types={"priority": "integer"},
        connection_attribute_types={},
        **limits,
    )


def _codes(definition: ViewpointDefinition, **limits: object) -> set[str]:
    return {issue.code for issue in _issues(definition, **limits)}


def test_duplicate_binding_and_parameter_names_have_addressable_paths() -> None:
    definition = _definition(
        bindings=(
            QueryBinding("items", EntitySetType(frozenset({"requirement"})), select="entities"),
            QueryBinding("items", EntitySetType(frozenset({"requirement"})), select="entities"),
        ),
        parameters=(QueryParameter("limit", "integer"), QueryParameter("limit", "integer")),
    )
    issues = _issues(definition)
    duplicate_paths = {issue.path for issue in issues if issue.code.startswith("duplicate-")}
    assert duplicate_paths == {"/query/bindings/1/name", "/query/parameters/1/name"}


@pytest.mark.parametrize(
    ("part", "limit", "code"),
    [
        ("bindings", "max_query_bindings", "binding-count-exceeded"),
        ("parameters", "max_query_parameters", "parameter-count-exceeded"),
        ("derived", "max_derived_attributes", "derived-attribute-count-exceeded"),
    ],
)
def test_declaration_limits_are_save_mode_errors(part: str, limit: str, code: str) -> None:
    binding = QueryBinding("items", EntitySetType(frozenset({"requirement"})), select="entities")
    parameter = QueryParameter("limit", "integer")
    derived = DerivedAttribute("total")
    definition = _definition(
        **{
            part: (binding, binding)
            if part == "bindings"
            else (parameter, parameter)
            if part == "parameters"
            else (derived, derived)
        }
    )
    assert code in _codes(definition, **{limit: 1})


def test_binding_type_and_result_shape_are_checked() -> None:
    definition = _definition(
        bindings=(QueryBinding("items", ScalarType("string"), select="entities", include_in_result=True),)
    )
    assert {"binding-type-mismatch", "include-in-result-shape-unsupported"} <= _codes(definition)


def test_non_count_derived_attribute_requires_a_source() -> None:
    definition = _definition(derived=(DerivedAttribute("largest", reduce="max"),))
    assert "derived-of-missing" in _codes(definition)


def test_list_binding_reference_requires_a_quantifier_or_aggregate() -> None:
    items = QueryBinding("items", EntitySetType(frozenset({"requirement"})), select="entities")
    query = ExecutableViewpointQuery(
        bindings=(items,),
        entity_criteria=EntityCriteriaGroup(
            children=(
                AttributeCondition(
                    attribute="priority",
                    comparator="eq",
                    value=ValueRef(kind="binding", binding="items", project="priority"),
                ),
            )
        ),
    )
    definition = ViewpointDefinition(slug="typed-query", version=1, name="Typed query", query=query)
    assert "unquantified-set-comparison" in _codes(definition)


def test_list_binding_reference_accepts_in_and_not_in_without_a_quantifier() -> None:
    items = QueryBinding("items", EntitySetType(frozenset({"requirement"})), select="entities")
    for comparator in ("in", "not_in"):
        query = ExecutableViewpointQuery(
            bindings=(items,),
            entity_criteria=EntityCriteriaGroup(
                children=(
                    AttributeCondition(
                        attribute="priority",
                        comparator=comparator,
                        value=ValueRef(kind="binding", binding="items", project="priority"),
                    ),
                )
            ),
        )
        definition = ViewpointDefinition(slug="typed-query", version=1, name="Typed query", query=query)
        # A projected-list binding reference is exactly what in/not_in exist to accept —
        # zero issues, not just an absent unquantified-set-comparison (a well-typed list
        # reference must not also be rejected as "not a list").
        assert _codes(definition) == set()


def test_tuple_binding_reference_supports_eq_in_not_in_but_rejects_other_comparators() -> None:
    identifiers = QueryBinding("identifiers", EntitySetType(frozenset({"requirement"})), select="entities")
    priorities = QueryBinding("priorities", EntitySetType(frozenset({"requirement"})), select="entities")
    pair = QueryBinding(
        "pair",
        TupleType((ScalarType("string"), ScalarType("integer"))),
        tuple_of=("identifiers", "priorities"),
    )

    def _codes_for(comparator: str) -> set[str]:
        query = ExecutableViewpointQuery(
            bindings=(identifiers, priorities, pair),
            entity_criteria=EntityCriteriaGroup(
                children=(
                    AttributeCondition(
                        attribute="priority", comparator=comparator, value=ValueRef(kind="binding", binding="pair")
                    ),
                )
            ),
        )
        definition = ViewpointDefinition(slug="typed-query", version=1, name="Typed query", query=query)
        return _codes(definition)

    for comparator in ("eq", "in", "not_in"):
        assert "tuple-comparator-unsupported" not in _codes_for(comparator)
    assert "tuple-comparator-unsupported" in _codes_for("lt")


def test_unknown_parameter_reference_has_criteria_path() -> None:
    query = ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(
            children=(
                AttributeCondition(
                    attribute="priority",
                    comparator="eq",
                    value=ValueRef(kind="parameter", parameter="missing"),
                ),
            )
        )
    )
    definition = ViewpointDefinition(slug="typed-query", version=1, name="Typed query", query=query)
    issues = _issues(definition)
    assert any(issue.code == "unknown-parameter" and issue.path.endswith("/value") for issue in issues)


def test_declaration_issues_carry_expected_and_found_values() -> None:
    definition = _definition(bindings=(QueryBinding("items", ScalarType("string"), select="entities"),))
    issues = _issues(definition)
    binding_issue = next(issue for issue in issues if issue.code == "binding-type-mismatch")
    assert binding_issue.path == "/query/bindings/0/result_type"
    assert binding_issue.expected is not None
    assert binding_issue.found is not None


def test_load_mode_skips_declaration_count_limits() -> None:
    binding = QueryBinding("items", EntitySetType(frozenset({"requirement"})), select="entities")
    definition = _definition(bindings=(binding, binding))
    issues = validate_viewpoint_definition(
        definition,
        mode="load",
        known_entity_types=frozenset({"requirement"}),
        known_connection_types=frozenset(),
        known_specialization_slugs=frozenset(),
        max_query_bindings=1,
    )
    assert "binding-count-exceeded" not in {issue.code for issue in issues}


def test_presentation_criteria_can_reference_query_parameters() -> None:
    match_criteria = EntityCriteriaGroup(
        children=(
            AttributeCondition(
                attribute="priority",
                comparator="eq",
                value=ValueRef(kind="parameter", parameter="priority"),
            ),
        )
    )
    definition = _definition(
        parameters=(QueryParameter("priority", "integer"),),
    )
    definition = ViewpointDefinition(
        slug=definition.slug,
        version=definition.version,
        name=definition.name,
        query=definition.query,
        presentation=PresentationSpec(
            representation="exploration",
            styling_rules=(StyleRule(capability="node_color", match_criteria=match_criteria, value="emphasis"),),
        ),
    )
    assert _issues(definition) == ()
