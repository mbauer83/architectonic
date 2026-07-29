"""The enum-set parameter type: canonicalization, parse/serialize round-trip, and validation
(min_items bounds, default subset + cardinality)."""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_binding_validation import QueryValueTypes, validate_query_values
from src.domain.viewpoints.viewpoint_bindings import QueryParameter
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_query_parsing import _parameter_from_mapping
from src.domain.viewpoints.viewpoint_query_serialization import _parameter_to_mapping
from src.domain.viewpoints.viewpoint_set_parameters import canonicalize_set_value

_ALLOWED = ("goal", "outcome", "requirement")
_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset(), known_connection_types=frozenset(), known_specialization_slugs=frozenset(),
    entity_attribute_types={}, connection_attribute_types={},
)


def _scope_mapping(**over: object) -> dict:
    return {
        "name": "scope", "type": "string", "cardinality": "many",
        "allowed_values": list(_ALLOWED), "min_items": 1, **over,
    }


def _issue_codes(parameter: QueryParameter) -> list[str]:
    issues, _ = validate_query_values(
        bindings=(), parameters=(parameter,), derived=(), path="q", registries=_REGISTRIES,
        check_ergonomics=True, max_bindings=8, max_parameters=8, max_derived_attributes=8,
    )
    return [i.code for i in issues]


class TestCanonicalize:
    def test_dedup_and_declaration_order(self) -> None:
        canonical, unknown = canonicalize_set_value(["requirement", "goal", "goal"], _ALLOWED)
        assert canonical == ("goal", "requirement")
        assert unknown == ()

    def test_reordering_canonicalizes_identically(self) -> None:
        a, _ = canonicalize_set_value(["requirement", "goal"], _ALLOWED)
        b, _ = canonicalize_set_value(["goal", "requirement"], _ALLOWED)
        assert a == b == ("goal", "requirement")

    def test_unknown_members_reported(self) -> None:
        canonical, unknown = canonicalize_set_value(["goal", "bogus", "bogus"], _ALLOWED)
        assert canonical == ("goal",)
        assert unknown == ("bogus",)


class TestParseSerialize:
    def test_parses_allowed_min_and_canonical_default(self) -> None:
        param = _parameter_from_mapping(_scope_mapping(default=["requirement", "goal"]))
        assert param.value_type == "string"
        assert param.cardinality == "many"
        assert param.allowed_values == _ALLOWED
        assert param.min_items == 1
        assert param.default == ("goal", "requirement")  # canonicalized

    def test_missing_allowed_values_rejected(self) -> None:
        with pytest.raises(ValueError, match="allowed_values"):
            _parameter_from_mapping({"name": "scope", "type": "string", "cardinality": "many", "allowed_values": []})

    def test_unknown_default_member_rejected(self) -> None:
        with pytest.raises(ValueError, match="outside allowed_values"):
            _parameter_from_mapping(_scope_mapping(default=["bogus"]))

    def test_round_trip(self) -> None:
        once = _parameter_from_mapping(_scope_mapping(default=["goal"]))
        twice = _parameter_from_mapping(_parameter_to_mapping(once))
        assert once == twice


class TestBindsIntoTheInCondition:
    """Regression: an enum-set parameter typed as a SCALAR reference made the shipped
    motivation-coverage viewpoint fail save-mode validation with 'in requires a list
    reference' — defeating the one binding this parameter type exists for: a set-valued
    parameter binds through the EXISTING `in` condition, with no separate guard grammar."""

    def test_enum_set_parameter_is_a_legal_in_operand(self) -> None:
        from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
        from src.domain.viewpoints.viewpoint_value_reference_validation import validate_query_value_references
        from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery

        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(AttributeCondition("type", "in", ValueRef(kind="parameter", parameter="scope")),)
            ),
            parameters=(_parameter_from_mapping(_scope_mapping()),),
        )
        issues = validate_query_value_references(
            query,
            values=QueryValueTypes(
                bindings={}, parameters={"scope": _parameter_from_mapping(_scope_mapping())}, derived={}
            ),
            path="/query",
            registries=_REGISTRIES,
            presentation=None,
        )
        assert [i for i in issues if i.code == "operator-type-mismatch"] == []


class TestValidation:
    def test_valid_enum_set_has_no_issues(self) -> None:
        assert _issue_codes(_parameter_from_mapping(_scope_mapping(default=["goal"]))) == []

    def test_min_items_out_of_range_flagged(self) -> None:
        bad = QueryParameter(
            name="scope",
            value_type="string",
            cardinality="many",
            allowed_values=_ALLOWED,
            min_items=0,
        )
        assert "set-parameter-invalid-min-items" in _issue_codes(bad)

    def test_default_below_min_items_flagged(self) -> None:
        bad = QueryParameter(
            name="scope", value_type="string", cardinality="many",
            allowed_values=_ALLOWED, min_items=2, default=("goal",),
        )
        assert "set-parameter-below-min-items" in _issue_codes(bad)

    def test_default_with_unknown_member_flagged(self) -> None:
        bad = QueryParameter(
            name="scope", value_type="string", cardinality="many",
            allowed_values=_ALLOWED, min_items=1, default=("bogus",),
        )
        assert "parameter-type-mismatch" in _issue_codes(bad)
