"""Tests for the WU-B3 typed-property spike: value ADT, lexical codec, validation."""
import pytest

from src.domain.ontology_representation.property_value import (
    SUPPORTED_SCHEMA_TYPES,
    check_schema_for_unsupported,
    decode,
    decode_lenient,
    decode_with_schema,
    encode,
    get_adhoc_type,
    validate,
)

# ---------------------------------------------------------------------------
# Markdown-cell escaping helpers (tested via encode/decode round-trip)
# ---------------------------------------------------------------------------


class TestMarkdownEscaping:
    def test_pipe_escaped_in_string(self):
        assert encode("a|b") == r"a\|b"

    def test_backslash_escaped_in_string(self):
        assert encode("a\\b") == r"a\\b"

    def test_newline_escaped_in_string(self):
        assert encode("a\nb") == r"a\nb"

    def test_combined_escaping(self):
        assert encode("a\\|b\nc") == r"a\\\|b\nc"

    def test_pipe_round_trip(self):
        original = "foo|bar"
        assert decode(encode(original), "string") == original

    def test_backslash_round_trip(self):
        original = "a\\b"
        assert decode(encode(original), "string") == original

    def test_newline_round_trip(self):
        original = "line1\nline2"
        assert decode(encode(original), "string") == original

    def test_backslash_then_newline_round_trip(self):
        original = "a\\\nb"  # backslash + newline
        assert decode(encode(original), "string") == original

    def test_double_backslash_round_trip(self):
        original = "a\\\\b"
        assert decode(encode(original), "string") == original


# ---------------------------------------------------------------------------
# Encode / decode round-trips per scalar type
# ---------------------------------------------------------------------------


class TestIntegerCodec:
    def test_encode_positive(self):
        assert encode(42) == "42"

    def test_encode_negative(self):
        assert encode(-7) == "-7"

    def test_encode_zero(self):
        assert encode(0) == "0"

    def test_decode_positive(self):
        assert decode("42", "integer") == 42

    def test_decode_negative(self):
        assert decode("-7", "integer") == -7

    def test_round_trip(self):
        for v in (0, 1, -1, 1_000_000):
            assert decode(encode(v), "integer") == v

    def test_decode_rejects_float_string(self):
        with pytest.raises(ValueError):
            decode("3.14", "integer")

    def test_decode_rejects_alpha(self):
        with pytest.raises(ValueError):
            decode("abc", "integer")


class TestNumberCodec:
    def test_encode_float(self):
        assert encode(3.14) == "3.14"

    def test_encode_whole(self):
        assert encode(1.0) == "1.0"

    def test_decode_float(self):
        assert decode("3.14", "number") == pytest.approx(3.14)

    def test_decode_int_string(self):
        # "42" is a valid number cell (parses as 42.0)
        assert decode("42", "number") == 42.0

    def test_round_trip(self):
        for v in (0.0, -1.5, 1e10, 3.14159):
            assert decode(encode(v), "number") == pytest.approx(v)

    def test_decode_rejects_alpha(self):
        with pytest.raises(ValueError):
            decode("abc", "number")


class TestBooleanCodec:
    def test_encode_true(self):
        assert encode(True) == "true"

    def test_encode_false(self):
        assert encode(False) == "false"

    def test_decode_true(self):
        assert decode("true", "boolean") is True

    def test_decode_false(self):
        assert decode("false", "boolean") is False

    def test_decode_rejects_capitalised(self):
        with pytest.raises(ValueError):
            decode("True", "boolean")

    def test_decode_rejects_one(self):
        with pytest.raises(ValueError):
            decode("1", "boolean")

    def test_bool_before_int(self):
        # encode(True) must be "true", not "1"
        assert encode(True) == "true"
        assert encode(False) == "false"


class TestArrayCodec:
    def test_encode_string_list(self):
        result = encode(["a", "b"])
        assert result == '["a","b"]'

    def test_encode_int_list(self):
        result = encode([1, 2, 3])
        assert result == "[1,2,3]"

    def test_encode_bool_list(self):
        result = encode([True, False])
        assert result == "[true,false]"

    def test_encode_mixed_scalars(self):
        result = encode([1, "x", True])
        assert result == '[1,"x",true]'

    def test_decode_string_list(self):
        assert decode('["a","b"]', "array") == ["a", "b"]

    def test_decode_int_list(self):
        assert decode("[1,2,3]", "array") == [1, 2, 3]

    def test_round_trip_simple(self):
        for v in ([], ["a", "b"], [1, 2], [True, False]):
            assert decode(encode(v), "array") == v

    def test_encode_escapes_pipe_in_element(self):
        # A pipe in a string element must be escaped for Markdown
        cell = encode(["a|b"])
        assert "|" not in cell.replace(r"\|", "")  # raw | gone
        assert decode(cell, "array") == ["a|b"]

    def test_decode_rejects_object(self):
        with pytest.raises(ValueError):
            decode('{"k":"v"}', "array")


# ---------------------------------------------------------------------------
# Schema-driven decode
# ---------------------------------------------------------------------------


class TestDecodeWithSchema:
    def test_string_schema(self):
        assert decode_with_schema("hello", {"type": "string"}) == "hello"

    def test_integer_schema(self):
        assert decode_with_schema("10", {"type": "integer"}) == 10

    def test_boolean_schema(self):
        assert decode_with_schema("true", {"type": "boolean"}) is True

    def test_missing_type_defaults_to_string(self):
        assert decode_with_schema("raw", {}) == "raw"

    def test_unsupported_type_returns_raw(self):
        assert decode_with_schema("raw", {"type": "object"}) == "raw"

    def test_unsupported_keyword_returns_raw(self):
        assert decode_with_schema("raw", {"type": "string", "oneOf": []}) == "raw"

    def test_enum_treated_as_string(self):
        schema = {"type": "string", "enum": ["A", "B"]}
        assert decode_with_schema("A", schema) == "A"

    def test_array_schema(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        assert decode_with_schema("[1,2,3]", schema) == [1, 2, 3]


# ---------------------------------------------------------------------------
# Lenient (migration-safe) decode
# ---------------------------------------------------------------------------


class TestDecodeLenient:
    def test_valid_integer(self):
        value, err = decode_lenient("42", {"type": "integer"})
        assert value == 42
        assert err is None

    def test_invalid_integer_returns_raw_string(self):
        value, err = decode_lenient("not-a-number", {"type": "integer"})
        assert value == "not-a-number"
        assert err is not None

    def test_invalid_boolean_returns_raw_string(self):
        value, err = decode_lenient("yes", {"type": "boolean"})
        assert value == "yes"
        assert err is not None

    def test_never_raises(self):
        # Should not raise for any inputs
        decode_lenient("anything", {"type": "integer"})
        decode_lenient("anything", {"type": "boolean"})
        decode_lenient("anything", {"type": "array"})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidate:
    def test_string_valid(self):
        assert validate("hello", {"type": "string"}) == []

    def test_string_enum_valid(self):
        assert validate("A", {"type": "string", "enum": ["A", "B"]}) == []

    def test_string_enum_invalid(self):
        errors = validate("C", {"type": "string", "enum": ["A", "B"]})
        assert len(errors) == 1
        assert "enum" in errors[0]

    def test_string_min_length(self):
        errors = validate("ab", {"type": "string", "minLength": 5})
        assert len(errors) == 1

    def test_string_max_length(self):
        errors = validate("abcdef", {"type": "string", "maxLength": 3})
        assert len(errors) == 1

    def test_string_pattern_valid(self):
        assert validate("abc123", {"type": "string", "pattern": r"^[a-z0-9]+$"}) == []

    def test_string_pattern_invalid(self):
        errors = validate("ABC", {"type": "string", "pattern": r"^[a-z]+$"})
        assert len(errors) == 1

    def test_integer_minimum(self):
        errors = validate(-1, {"type": "integer", "minimum": 0})
        assert len(errors) == 1

    def test_integer_maximum(self):
        errors = validate(11, {"type": "integer", "maximum": 10})
        assert len(errors) == 1

    def test_integer_in_range(self):
        assert validate(5, {"type": "integer", "minimum": 0, "maximum": 10}) == []

    def test_number_in_range(self):
        assert validate(3.14, {"type": "number", "minimum": 0.0, "maximum": 10.0}) == []

    def test_boolean_valid(self):
        assert validate(True, {"type": "boolean"}) == []
        assert validate(False, {"type": "boolean"}) == []

    def test_boolean_rejects_string(self):
        errors = validate("true", {"type": "boolean"})
        assert len(errors) == 1

    def test_array_valid(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        assert validate([1, 2, 3], schema) == []

    def test_array_item_violation(self):
        schema = {"type": "array", "items": {"type": "integer", "minimum": 0}}
        errors = validate([1, -1, 2], schema)
        assert len(errors) == 1
        assert "[1]" in errors[0]

    def test_wrong_type_returns_error(self):
        errors = validate("hello", {"type": "integer"})
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# Startup unsupported-construct detection
# ---------------------------------------------------------------------------


class TestCheckSchemaForUnsupported:
    def test_clean_string_schema(self):
        assert check_schema_for_unsupported("MyProp", {"type": "string"}) == []

    def test_null_type_flagged(self):
        findings = check_schema_for_unsupported("MyProp", {"type": "null"})
        assert len(findings) == 1
        assert "MyProp" in findings[0]

    def test_object_type_flagged(self):
        findings = check_schema_for_unsupported("MyProp", {"type": "object"})
        assert len(findings) == 1

    def test_oneof_flagged(self):
        findings = check_schema_for_unsupported("MyProp", {"oneOf": [{"type": "string"}]})
        assert len(findings) == 1
        assert "oneOf" in findings[0]

    def test_nested_array_flagged(self):
        schema = {"type": "array", "items": {"type": "array"}}
        findings = check_schema_for_unsupported("MyProp", schema)
        assert len(findings) == 1

    def test_tuple_array_flagged(self):
        schema = {"type": "array", "items": [{"type": "string"}, {"type": "integer"}]}
        findings = check_schema_for_unsupported("MyProp", schema)
        assert len(findings) == 1

    def test_supported_array_no_findings(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        assert check_schema_for_unsupported("MyProp", schema) == []


# ---------------------------------------------------------------------------
# Ad-hoc type carrier
# ---------------------------------------------------------------------------


class TestGetAdhocType:
    def test_declared_integer(self):
        assert get_adhoc_type("MyField", {"MyField": "integer"}) == "integer"

    def test_declared_boolean(self):
        assert get_adhoc_type("Flag", {"Flag": "boolean"}) == "boolean"

    def test_undeclared_defaults_to_string(self):
        assert get_adhoc_type("Unknown", {}) == "string"

    def test_unsupported_declared_type_degrades(self):
        # "object" is not in SUPPORTED_SCHEMA_TYPES → returns "string"
        assert get_adhoc_type("Bad", {"Bad": "object"}) == "string"

    def test_all_supported_types_accepted(self):
        for t in SUPPORTED_SCHEMA_TYPES:
            result = get_adhoc_type("X", {"X": t})
            assert result == t


# ---------------------------------------------------------------------------
# Full round-trip: encode → decode for all scalar types + migration scenario
# ---------------------------------------------------------------------------


class TestFullRoundTrip:
    def test_string_round_trip(self):
        for v in ("", "hello", "a|b\\c\nd", "  spaces  "):
            cell = encode(v)
            assert decode(cell, "string") == v

    def test_integer_round_trip_via_schema(self):
        schema = {"type": "integer"}
        for v in (0, -1, 42, 1_000_000):
            cell = encode(v)
            assert decode_with_schema(cell, schema) == v

    def test_number_round_trip_via_schema(self):
        schema = {"type": "number"}
        for v in (0.0, -1.5, 3.14159, 1e10):
            cell = encode(v)
            assert decode_with_schema(cell, schema) == pytest.approx(v)

    def test_boolean_round_trip_via_schema(self):
        schema = {"type": "boolean"}
        for v in (True, False):
            cell = encode(v)
            assert decode_with_schema(cell, schema) is v

    def test_array_round_trip_via_schema(self):
        schema = {"type": "array", "items": {"type": "string"}}
        v = ["alpha", "beta|gamma", "delta\\epsilon"]
        cell = encode(v)
        assert decode_with_schema(cell, schema) == v

    def test_migration_existing_string_as_string_schema(self):
        # Legacy cells already stored as strings decode cleanly under string schema
        existing_cell = "Initial"
        schema = {"type": "string"}
        value, err = decode_lenient(existing_cell, schema)
        assert value == "Initial"
        assert err is None

    def test_migration_existing_integer_string_under_integer_schema(self):
        # "42" was stored as a plain string; now schema says integer
        value, err = decode_lenient("42", {"type": "integer"})
        assert value == 42
        assert err is None

    def test_migration_bad_cell_for_integer_schema_returns_raw_string(self):
        # "forty-two" cannot parse as integer → raw string returned with error
        value, err = decode_lenient("forty-two", {"type": "integer"})
        assert value == "forty-two"  # preserved as-is
        assert err is not None
