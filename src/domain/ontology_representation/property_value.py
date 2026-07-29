"""
Typed-property value model: ADT, canonical lexical codec, schema-driven decode.

This is the WU-B3 spike deliverable. After OQ-2 review, the full port follows
(threading through parser / formatter / REST / MCP / GUI).

Canonical Lexical Grammar (how values are stored in Markdown table cells)
--------------------------------------------------------------------------
  type      canonical form             Markdown-cell escaping applied?
  string    verbatim                   YES: \\ → \\\\  |  →  \\|  LF → \\n
  integer   -?[0-9]+                   no (safe chars only)
  number    Python str(float) form     no (safe chars only)
  boolean   "true" or "false"          no (safe chars only)
  enum      verbatim string value      YES (same as string)
  array     compact JSON               YES (applied to the JSON output)

Deferred (not in the supported subset):
  null, object, oneOf/anyOf/allOf, patternProperties, nested arrays, tuple arrays.
  A schema using these produces a startup warning; values are treated as raw strings.

Migration / backward-compatibility
------------------------------------
  Existing entities store all property values as strings (dict[str, str]).
  * Schema-declared attributes: decoded on read using the property's schema type.
    Cells that cannot parse emit a W-category warning and are returned as raw strings
    (fail-soft on read; canonical re-emission enforced on next write).
  * Ad-hoc attributes (not in the schema): carry their type via the
    ``attribute_types`` key in the entity's YAML frontmatter (see below).
    Missing → defaults to "string" (preserves existing behaviour).

Ad-hoc attribute type carrier
------------------------------
  Entity frontmatter carries an optional ``attribute_types`` map:

      attribute_types:
        MyIntField: integer
        MyBoolField: boolean

  Schema-declared attributes IGNORE this map; their type comes from the schema.
  Only types in SUPPORTED_SCHEMA_TYPES are valid; anything else degrades to "string".
"""
from __future__ import annotations

import json
import re
from typing import Union

# ---------------------------------------------------------------------------
# Value ADT
# ---------------------------------------------------------------------------

PropertyScalar = Union[str, int, float, bool]
# list is always a homogeneous scalar array (list[PropertyScalar])
PropertyValue = Union[PropertyScalar, "list[PropertyScalar]"]

# Supported JSON-Schema type strings for the codec
SUPPORTED_SCHEMA_TYPES: frozenset[str] = frozenset(
    {"string", "integer", "number", "boolean", "array"}
)
# Types that are explicitly unsupported (emit startup warning, not hard failure)
UNSUPPORTED_SCHEMA_TYPES: frozenset[str] = frozenset({"null", "object"})
# Keywords that disqualify a property from typed decode
UNSUPPORTED_KEYWORDS: tuple[str, ...] = (
    "oneOf", "anyOf", "allOf", "$ref", "if", "then", "else",
)

# Frontmatter key used by the ad-hoc type carrier
AD_HOC_TYPE_CARRIER_KEY = "attribute_types"

# ---------------------------------------------------------------------------
# Markdown-cell escaping
# ---------------------------------------------------------------------------

_SENTINEL = "\x00BACKSLASH\x00"  # Never appears in real content


def _md_escape(text: str) -> str:
    """Escape a string for safe embedding in a Markdown table cell."""
    return (
        text
        .replace("\\", "\\\\")  # must come first
        .replace("|", "\\|")
        .replace("\n", "\\n")
    )


def _md_unescape(cell: str) -> str:
    r"""Reverse _md_escape. Sentinel prevents double-unescaping \\  →  \ ."""
    return (
        cell
        .replace("\\\\", _SENTINEL)
        .replace("\\|", "|")
        .replace("\\n", "\n")
        .replace(_SENTINEL, "\\")
    )


# ---------------------------------------------------------------------------
# Encoding: PropertyValue → canonical Markdown cell string
# ---------------------------------------------------------------------------

def encode(value: PropertyValue) -> str:
    """Encode a typed value to its canonical Markdown table cell string."""
    if isinstance(value, bool):  # bool before int (bool is a subclass of int)
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return _md_escape(value)
    if isinstance(value, list):
        return _md_escape(json.dumps(value, separators=(",", ":")))
    raise TypeError(f"Unsupported PropertyValue type: {type(value).__name__}")


# ---------------------------------------------------------------------------
# Decoding: Markdown cell string × schema type → PropertyValue
# ---------------------------------------------------------------------------

def decode(cell: str, schema_type: str) -> PropertyValue:
    """
    Decode a Markdown table cell string to a typed value.

    Raises ValueError if the cell cannot be decoded as *schema_type*.
    Callers that need migration-safe behaviour should use decode_lenient().
    """
    if schema_type == "string":
        return _md_unescape(cell)
    if schema_type == "integer":
        if not re.fullmatch(r"-?[0-9]+", cell.strip()):
            raise ValueError(f"Cannot decode {cell!r} as integer")
        return int(cell.strip())
    if schema_type == "number":
        try:
            return float(cell.strip())
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"Cannot decode {cell!r} as number") from exc
    if schema_type == "boolean":
        if cell == "true":
            return True
        if cell == "false":
            return False
        raise ValueError(
            f"Cannot decode {cell!r} as boolean; expected literal 'true' or 'false'"
        )
    if schema_type == "array":
        raw = _md_unescape(cell)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Cannot decode {cell!r} as array: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError(
                f"Decoded value is not an array: {type(parsed).__name__}"
            )
        return parsed
    raise ValueError(f"Unsupported schema type {schema_type!r}")


def decode_with_schema(cell: str, prop_schema: dict) -> PropertyValue:
    """
    Schema-driven decode: consult a JSON-Schema property descriptor to choose the type.

    Falls back to 'string' for unsupported types/keywords (legacy-safe).
    Raises ValueError on type mismatch (e.g. 'abc' for type 'integer').
    """
    schema_type = prop_schema.get("type", "string")
    if schema_type not in SUPPORTED_SCHEMA_TYPES:
        return _md_unescape(cell)
    for kw in UNSUPPORTED_KEYWORDS:
        if kw in prop_schema:
            return _md_unescape(cell)
    return decode(cell, schema_type)


def decode_lenient(
    cell: str, prop_schema: dict
) -> tuple[PropertyValue, str | None]:
    """
    Migration-safe decode.  Returns (value, None) on success or
    (raw_string, error_message) on parse failure.  Never raises.
    """
    try:
        return decode_with_schema(cell, prop_schema), None
    except (ValueError, TypeError) as exc:
        return _md_unescape(cell), str(exc)


# ---------------------------------------------------------------------------
# Validation: PropertyValue × JSON-Schema property descriptor → violations
# ---------------------------------------------------------------------------

def validate(value: PropertyValue, prop_schema: dict) -> list[str]:
    """Return constraint violation messages (empty list = valid)."""
    errors: list[str] = []
    schema_type = prop_schema.get("type", "string")

    if schema_type == "string":
        if not isinstance(value, str):
            return [f"Expected string, got {type(value).__name__}"]
        if "enum" in prop_schema and value not in prop_schema["enum"]:
            errors.append(f"Value {value!r} not in enum {prop_schema['enum']}")
        if "minLength" in prop_schema and len(value) < prop_schema["minLength"]:
            errors.append(f"Too short: {len(value)} < minLength {prop_schema['minLength']}")
        if "maxLength" in prop_schema and len(value) > prop_schema["maxLength"]:
            errors.append(f"Too long: {len(value)} > maxLength {prop_schema['maxLength']}")
        if "pattern" in prop_schema and not re.search(prop_schema["pattern"], value):
            errors.append(
                f"Value {value!r} does not match pattern {prop_schema['pattern']!r}"
            )

    elif schema_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"Expected integer, got {type(value).__name__}"]
        _validate_numeric(value, prop_schema, errors)

    elif schema_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return [f"Expected number, got {type(value).__name__}"]
        _validate_numeric(value, prop_schema, errors)

    elif schema_type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"Expected boolean, got {type(value).__name__}")

    elif schema_type == "array":
        if not isinstance(value, list):
            return [f"Expected array, got {type(value).__name__}"]
        items_schema = prop_schema.get("items", {"type": "string"})
        for idx, item in enumerate(value):
            for msg in validate(item, items_schema):
                errors.append(f"[{idx}]: {msg}")

    return errors


def _validate_numeric(
    value: int | float, prop_schema: dict, errors: list[str]
) -> None:
    if "minimum" in prop_schema and value < prop_schema["minimum"]:
        errors.append(f"{value} < minimum {prop_schema['minimum']}")
    if "maximum" in prop_schema and value > prop_schema["maximum"]:
        errors.append(f"{value} > maximum {prop_schema['maximum']}")
    if "exclusiveMinimum" in prop_schema and value <= prop_schema["exclusiveMinimum"]:
        errors.append(f"{value} ≤ exclusiveMinimum {prop_schema['exclusiveMinimum']}")
    if "exclusiveMaximum" in prop_schema and value >= prop_schema["exclusiveMaximum"]:
        errors.append(f"{value} ≥ exclusiveMaximum {prop_schema['exclusiveMaximum']}")


# ---------------------------------------------------------------------------
# Startup check: flag unsupported schema constructs (non-blocking finding)
# ---------------------------------------------------------------------------

def check_schema_for_unsupported(prop_name: str, prop_schema: dict) -> list[str]:
    """
    Return startup-finding messages for unsupported schema constructs on *prop_name*.
    Called from startup_validation.py for each declared property when schemas load.
    Findings are non-blocking (the property degrades to raw-string behaviour).
    """
    findings: list[str] = []
    schema_type = prop_schema.get("type")
    if schema_type in UNSUPPORTED_SCHEMA_TYPES:
        findings.append(
            f"Property '{prop_name}': type '{schema_type}' is not supported by the "
            "typed-property codec; values will be stored and returned as raw strings."
        )
    for kw in UNSUPPORTED_KEYWORDS:
        if kw in prop_schema:
            findings.append(
                f"Property '{prop_name}': keyword '{kw}' is not supported by the "
                "typed-property codec; values will be treated as raw strings."
            )
    if schema_type == "array":
        items = prop_schema.get("items", {})
        if isinstance(items, dict) and items.get("type") == "array":
            findings.append(
                f"Property '{prop_name}': nested arrays are not supported; "
                "items will be treated as raw strings."
            )
        if isinstance(items, list):
            findings.append(
                f"Property '{prop_name}': tuple-typed arrays (items as list) "
                "are not supported; values will be treated as raw strings."
            )
    return findings


# ---------------------------------------------------------------------------
# Ad-hoc attribute type carrier helpers
# ---------------------------------------------------------------------------

def get_adhoc_type(attr_name: str, attribute_types: dict[str, str]) -> str:
    """
    Look up the declared type for an ad-hoc (non-schema) attribute.
    Returns 'string' when undeclared (preserves existing behaviour for legacy cells).
    Degrades to 'string' silently if the declared type is not in SUPPORTED_SCHEMA_TYPES.
    """
    declared = attribute_types.get(attr_name, "string")
    if declared not in SUPPORTED_SCHEMA_TYPES:
        return "string"
    return declared
