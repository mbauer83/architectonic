"""Structured grammar reference for viewpoint authoring and execution."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_criteria import (
    RESERVED_CONNECTION_PATHS,
    RESERVED_ENTITY_PATHS,
    VALID_VALUE_REF_KINDS,
)
from src.domain.viewpoints.viewpoints import QUERY_SCHEMA_VERSION, REPRESENTATION_CAPABILITIES

_COMPARATOR_SEMANTICS: dict[str, str] = {
    "eq": "equal; a multi-valued attribute matches if any element equals the value",
    "neq": "not equal; a multi-valued attribute matches only if no element equals the value",
    "in": "value is one of a list; a multi-valued attribute matches if any element is in the list",
    "exists": "attribute is present (no value operand)",
    "absent": "attribute is missing (no value operand) — the only comparator matching a missing attribute",
    "lt": "less than (numeric/date attributes only)",
    "lte": "at most (numeric/date attributes only)",
    "gt": "greater than (numeric/date attributes only)",
    "gte": "at least (numeric/date attributes only)",
}

_CANONICAL_FORM_EXAMPLE: dict[str, object] = {
    "query_schema": QUERY_SCHEMA_VERSION,
    "entity_criteria": {
        "kind": "group",
        "conjunction": "and",
        "children": [
            {"kind": "condition", "attribute": "type", "comparator": "in", "value": ["application-component"]}
        ],
    },
}


def viewpoints_help_topic() -> dict[str, object]:
    """Return the grammar, comparator behavior, and structured query vocabulary."""
    return {
        "query_schema": QUERY_SCHEMA_VERSION,
        "comparators": _COMPARATOR_SEMANTICS,
        "value_ref_kinds": sorted(VALID_VALUE_REF_KINDS),
        "reserved_entity_paths": sorted(RESERVED_ENTITY_PATHS),
        "reserved_connection_paths": sorted(RESERVED_CONNECTION_PATHS),
        "representation_capabilities": {
            representation: sorted(capabilities) for representation, capabilities in REPRESENTATION_CAPABILITIES.items()
        },
        "canonical_form_example": _CANONICAL_FORM_EXAMPLE,
        "bindings": {
            "select": ["entities", "connections"],
            "result_types": ["entity[type]", "connection[type]", "entities[type]", "connections[type]", "scalar"],
            "quantifiers": ["any", "all"],
        },
        "parameters": {"types": ["string", "integer", "number", "date", "boolean", "slug", "entity-id"]},
        "derived_attributes": {
            "traversal": ["direct", "derived"],
            "certainty": ["certain", "potential"],
            "sources": ["connection.attribute", "endpoint.attribute", "relationship.hops"],
        },
        "notes": (
            "negate is the strict logical complement: 'eq' + negate on a missing attribute "
            "matches — it reads as 'is not X, or has no value', not 'has X removed'. Connection "
            "endpoints are not addressable as left-hand condition paths; compare against an "
            "endpoint's attribute with a ValueRef(kind=attribute_of_endpoint) value instead."
        ),
    }
