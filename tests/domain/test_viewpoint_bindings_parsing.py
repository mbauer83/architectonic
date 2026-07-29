"""Structural parsing tests for binding, parameter, and derived query declarations."""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping


def _query_with(**extra: object) -> object:
    return query_from_mapping(
        {
            "query_schema": 1,
            "entity_criteria": {"kind": "group", "conjunction": "and", "children": []},
            **extra,
        },
        label="test",
    )


def test_parses_binding_parameter_and_derived_attribute() -> None:
    query = _query_with(
        bindings=[{"name": "components", "result_type": "entities[application-component]", "select": "entities"}],
        parameters=[{"name": "limit", "type": "integer"}],
        derived=[{"name": "count", "traversal": "derived", "max_hops": 2}],
    )

    assert query.bindings[0].name == "components"
    assert query.parameters[0].value_type == "integer"
    assert query.derived[0].traversal == "derived"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("bindings", [{"name": "x", "result_type": "string", "unknown": True}], "unknown key"),
        ("parameters", [{"name": "x", "type": "unknown"}], "parameter type"),
        ("derived", [{"name": "x", "traversal": "unknown"}], "traversal"),
    ],
)
def test_invalid_declaration_fields_are_rejected(field: str, value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _query_with(**{field: value})
