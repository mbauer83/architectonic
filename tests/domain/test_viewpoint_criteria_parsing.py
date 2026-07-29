"""Direct tests for the criteria-tree parser/serializer:
kind discrimination, ValueRef literal-vs-mapping forms, unknown-key rejection, and
round-trip identity, independent of the top-level definition parsing tested elsewhere."""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
    ValueRef,
)
from src.domain.viewpoints.viewpoint_criteria_parsing import (
    parse_connection_criteria_group,
    parse_entity_criteria_group,
    parse_entity_criteria_node,
)
from src.domain.viewpoints.viewpoint_criteria_serialization import (
    connection_criteria_group_to_mapping,
    entity_criteria_group_to_mapping,
)


class TestKindDiscrimination:
    def test_unknown_kind_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown entity criteria node kind"):
            parse_entity_criteria_node({"kind": "bogus"})

    def test_condition_requires_kind_condition(self) -> None:
        node = parse_entity_criteria_node({"kind": "condition", "attribute": "type", "comparator": "eq", "value": "x"})
        assert isinstance(node, AttributeCondition)

    def test_incident_kind_produces_incident_condition(self) -> None:
        node = parse_entity_criteria_node({"kind": "incident"})
        assert isinstance(node, IncidentConnectionCondition)
        assert node.connection_criteria is None
        assert node.endpoint_criteria is None

    def test_connection_criteria_field_requires_kind_group(self) -> None:
        with pytest.raises(ValueError, match="expected a connection criteria group"):
            parse_entity_criteria_node(
                {
                    "kind": "incident",
                    "connection_criteria": {"kind": "condition", "attribute": "type", "comparator": "eq", "value": "x"},
                }
            )

    def test_endpoint_criteria_field_requires_kind_group(self) -> None:
        with pytest.raises(ValueError, match="expected an entity criteria group"):
            parse_entity_criteria_node(
                {
                    "kind": "incident",
                    "endpoint_criteria": {"kind": "condition", "attribute": "type", "comparator": "eq", "value": "x"},
                }
            )

    def test_incident_kind_not_allowed_inside_connection_criteria(self) -> None:
        with pytest.raises(ValueError, match="unknown connection criteria node kind"):
            parse_connection_criteria_group({"kind": "group", "conjunction": "and", "children": [{"kind": "incident"}]})


class TestUnknownKeys:
    def test_unknown_key_in_condition_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown key"):
            parse_entity_criteria_node(
                {"kind": "condition", "attribute": "type", "comparator": "eq", "value": "x", "bogus": 1}
            )

    def test_unknown_key_in_group_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown key"):
            parse_entity_criteria_group({"kind": "group", "children": [], "bogus": 1})

    def test_unknown_key_in_value_ref_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown key"):
            parse_entity_criteria_node(
                {
                    "kind": "condition",
                    "attribute": "type",
                    "comparator": "eq",
                    "value": {"from": "self", "attribute": "x", "bogus": 1},
                }
            )


class TestComparatorVocabulary:
    @pytest.mark.parametrize("comparator", ["not_in", "like", "ilike"])
    def test_new_comparators_parse(self, comparator: str) -> None:
        node = parse_entity_criteria_node(
            {"kind": "condition", "attribute": "name", "comparator": comparator, "value": "x"}
        )
        assert isinstance(node, AttributeCondition)
        assert node.comparator == comparator

    def test_unknown_comparator_rejected(self) -> None:
        with pytest.raises(ValueError, match="comparator"):
            parse_entity_criteria_node({"kind": "condition", "attribute": "name", "comparator": "bogus", "value": "x"})

    def test_not_in_like_ilike_round_trip(self) -> None:
        group = EntityCriteriaGroup(
            children=(
                AttributeCondition(attribute="type", comparator="not_in", value=ValueRef(literal=["a", "b"])),
                AttributeCondition(attribute="name", comparator="like", value=ValueRef(literal="%Service")),
                AttributeCondition(attribute="name", comparator="ilike", value=ValueRef(literal="%service%")),
            )
        )
        mapping = entity_criteria_group_to_mapping(group)
        reparsed = parse_entity_criteria_group(mapping)
        assert reparsed == group


class TestValueRefForms:
    def test_literal_shorthand(self) -> None:
        condition = parse_entity_criteria_node(
            {"kind": "condition", "attribute": "type", "comparator": "eq", "value": "process"}
        )
        assert isinstance(condition, AttributeCondition)
        assert condition.value == ValueRef(kind="literal", literal="process")

    def test_list_literal_shorthand(self) -> None:
        condition = parse_entity_criteria_node(
            {"kind": "condition", "attribute": "type", "comparator": "in", "value": ["a", "b"]}
        )
        assert isinstance(condition, AttributeCondition)
        assert condition.value.literal == ["a", "b"]

    def test_self_reference_mapping_form(self) -> None:
        condition = parse_entity_criteria_node(
            {
                "kind": "condition",
                "attribute": "end_date",
                "comparator": "gte",
                "value": {"from": "self", "attribute": "start_date"},
            }
        )
        assert isinstance(condition, AttributeCondition)
        assert condition.value == ValueRef(kind="attribute_of_self", attribute="start_date")

    def test_endpoint_reference_mapping_form(self) -> None:
        condition = parse_entity_criteria_node(
            {
                "kind": "condition",
                "attribute": "strength",
                "comparator": "gte",
                "value": {"from": "target", "attribute": "threshold"},
            }
        )
        assert isinstance(condition, AttributeCondition)
        assert condition.value == ValueRef(kind="attribute_of_endpoint", attribute="threshold", endpoint="target")

    def test_binding_reference_mapping_form(self) -> None:
        condition = parse_entity_criteria_node(
            {
                "kind": "condition",
                "attribute": "owner",
                "comparator": "eq",
                "value": {"from": "binding", "name": "owners", "project": "id", "quantifier": "any"},
            }
        )
        assert isinstance(condition, AttributeCondition)
        assert condition.value == ValueRef(kind="binding", binding="owners", project="id", quantifier="any")

    def test_parameter_reference_mapping_form(self) -> None:
        condition = parse_entity_criteria_node(
            {
                "kind": "condition",
                "attribute": "criticality",
                "comparator": "eq",
                "value": {"from": "parameter", "name": "minimum_criticality"},
            }
        )
        assert isinstance(condition, AttributeCondition)
        assert condition.value == ValueRef(kind="parameter", parameter="minimum_criticality")

    def test_invalid_from_value_rejected(self) -> None:
        with pytest.raises(ValueError, match="from"):
            parse_entity_criteria_node(
                {
                    "kind": "condition",
                    "attribute": "x",
                    "comparator": "eq",
                    "value": {"from": "sideways", "attribute": "y"},
                }
            )


class TestRoundTrip:
    def test_negate_only_written_when_true(self) -> None:
        group = EntityCriteriaGroup(
            children=(AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="x")),)
        )
        mapping = entity_criteria_group_to_mapping(group)
        assert "negate" not in mapping["children"][0]

        negated = EntityCriteriaGroup(
            children=(AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="x"), negate=True),)
        )
        mapping2 = entity_criteria_group_to_mapping(negated)
        assert mapping2["children"][0]["negate"] is True

    def test_default_value_omitted_on_write(self) -> None:
        condition = AttributeCondition(attribute="active", comparator="exists")
        group = EntityCriteriaGroup(children=(condition,))
        mapping = entity_criteria_group_to_mapping(group)
        assert "value" not in mapping["children"][0]

    def test_connection_group_round_trips(self) -> None:
        group = ConnectionCriteriaGroup(
            children=(
                AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="archimate-serving")),
            )
        )
        mapping = connection_criteria_group_to_mapping(group)
        reparsed = parse_connection_criteria_group(mapping)
        assert reparsed == group
