"""Unit tests for the criteria-engine value objects: comparator vocabulary, value
references, and criteria-tree node shapes."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_criteria import (
    RESERVED_CONNECTION_PATHS,
    RESERVED_ENTITY_PATHS,
    VALID_COMPARATORS,
    AttributeCondition,
    ConnectionCriteriaGroup,
    ConnectionSelection,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
    NeighborInclusion,
    ValueRef,
)


class TestValueRef:
    def test_default_is_literal_none(self) -> None:
        ref = ValueRef()
        assert ref.kind == "literal"
        assert ref.literal is None
        assert ref.attribute is None
        assert ref.endpoint is None

    def test_attribute_of_endpoint(self) -> None:
        ref = ValueRef(kind="attribute_of_endpoint", attribute="threshold", endpoint="target")
        assert ref.kind == "attribute_of_endpoint"
        assert ref.endpoint == "target"


class TestAttributeCondition:
    def test_defaults(self) -> None:
        condition = AttributeCondition(attribute="type", comparator="eq", value=ValueRef(kind="literal", literal="x"))
        assert condition.negate is False

    def test_comparator_vocabulary_matches_valid_comparators(self) -> None:
        assert VALID_COMPARATORS == {
            "eq",
            "neq",
            "in",
            "not_in",
            "exists",
            "absent",
            "lt",
            "lte",
            "gt",
            "gte",
            "like",
            "ilike",
        }


class TestCriteriaGroups:
    def test_entity_group_nests_incident_condition(self) -> None:
        group = EntityCriteriaGroup(
            conjunction="and",
            children=(
                AttributeCondition(attribute="type", comparator="eq", value=ValueRef(kind="literal", literal="a")),
                IncidentConnectionCondition(
                    connection_criteria=ConnectionCriteriaGroup(
                        children=(
                            AttributeCondition(
                                attribute="type", comparator="eq", value=ValueRef(kind="literal", literal="serving")
                            ),
                        )
                    ),
                    endpoint_criteria=EntityCriteriaGroup(
                        children=(
                            AttributeCondition(
                                attribute="type", comparator="eq", value=ValueRef(kind="literal", literal="process")
                            ),
                        )
                    ),
                ),
            ),
        )
        assert len(group.children) == 2
        assert isinstance(group.children[1], IncidentConnectionCondition)

    def test_incident_condition_recurses_via_endpoint_criteria(self) -> None:
        inner = IncidentConnectionCondition()
        outer_endpoint = EntityCriteriaGroup(children=(inner,))
        outer = IncidentConnectionCondition(endpoint_criteria=outer_endpoint)
        assert outer.endpoint_criteria is outer_endpoint
        assert outer.endpoint_criteria.children[0] is inner

    def test_group_negate_default_false(self) -> None:
        assert EntityCriteriaGroup().negate is False
        assert ConnectionCriteriaGroup().negate is False

    def test_empty_root_group_is_representable(self) -> None:
        assert EntityCriteriaGroup().children == ()


class TestConnectionSelection:
    def test_default_enabled_with_empty_criteria(self) -> None:
        selection = ConnectionSelection()
        assert selection.enabled is True
        assert selection.criteria.children == ()

    def test_disabled(self) -> None:
        assert ConnectionSelection(enabled=False).enabled is False


class TestNeighborInclusion:
    def test_defaults_match_anything(self) -> None:
        inclusion = NeighborInclusion()
        assert inclusion.connection_criteria is None
        assert inclusion.neighbor_criteria is None
        assert inclusion.direction == "either"

    def test_direction_relative_to_anchor(self) -> None:
        inclusion = NeighborInclusion(direction="outgoing")
        assert inclusion.direction == "outgoing"


class TestReservedPaths:
    def test_entity_paths_include_version_as_string_only(self) -> None:
        assert "version" in RESERVED_ENTITY_PATHS

    def test_connection_paths_are_a_narrower_set(self) -> None:
        assert RESERVED_CONNECTION_PATHS <= RESERVED_ENTITY_PATHS
        assert RESERVED_CONNECTION_PATHS == {"id", "type", "specialization"}
