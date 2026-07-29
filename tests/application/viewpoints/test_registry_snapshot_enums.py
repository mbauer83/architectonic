"""Enum extraction for the criteria value picker: an attribute's JSON-schema ``enum``
becomes an enumerable value set the builder offers as a dropdown/multi-select instead of a
free-text field. Only non-empty string enums are surfaced."""

from __future__ import annotations

from src.application.viewpoints.registry_snapshot import _property_enums


def test_extracts_string_enum_values() -> None:
    schema = {"properties": {"Priority": {"type": "string", "enum": ["Must", "Should", "Could"]}}}
    assert _property_enums(schema) == {"Priority": ("Must", "Should", "Could")}


def test_skips_attributes_without_enum() -> None:
    schema = {"properties": {"name": {"type": "string"}, "score": {"type": "number"}}}
    assert _property_enums(schema) == {}


def test_skips_empty_enum() -> None:
    schema = {"properties": {"Category": {"type": "string", "enum": []}}}
    assert _property_enums(schema) == {}


def test_coerces_non_string_enum_members_to_str() -> None:
    schema = {"properties": {"Level": {"enum": [1, 2, 3]}}}
    assert _property_enums(schema) == {"Level": ("1", "2", "3")}


def test_a_string_enum_value_is_not_treated_as_a_sequence() -> None:
    # A bare string ``enum`` (malformed) must not be exploded into per-character choices.
    schema = {"properties": {"Bad": {"enum": "abc"}}}
    assert _property_enums(schema) == {}


def test_handles_missing_or_malformed_schema() -> None:
    assert _property_enums(None) == {}
    assert _property_enums({}) == {}
    assert _property_enums({"properties": "not-a-mapping"}) == {}
