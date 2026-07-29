"""Derive a JSON Schema for diagram_entities from diagram ontology declarations.

Management fields (id, label) are auto-injected into every entity schema.
An optional nested ``binding`` shorthand field is also injected — normalized to
top-level ``bindings`` on write (see binding_normalize.normalize_bindings).
Only domain-specific properties need to be declared in ontology.yaml.

Every entity type declared in the diagram type's ontology automatically gets its own
top-level array in diagram-entities, keyed by the entity type name.  There is no distinction
between "embedded" and "non-embedded" entity types — all persist in the same flat
per-entity-type structure.  Connection semantics (embedding, cascade-delete, etc.) are
a relationship concern, not a data-persistence concern.
"""

from __future__ import annotations

from src.domain.diagrams.bindings import BINDING_SHORTHAND_SCHEMA, BINDINGS_ARRAY_SCHEMA
from src.domain.ontology_representation.ontology_protocol import (
    DiagramOwnEntityTypePropertySpec,
    DiagramOwnEntityTypeUiConfig,
)


def derive_diagram_entities_schema(
    own_types: tuple[DiagramOwnEntityTypeUiConfig, ...],
) -> dict[str, object] | None:
    """Return a JSON Schema for diagram_entities, or None if there are no entity types.

    Each entity type in ``own_types`` produces a top-level array in diagram-entities keyed
    by its entity type name.
    """
    if not own_types:
        return None

    props: dict[str, object] = {}
    defs: dict[str, object] = {}

    for et in own_types:
        defs[et.entity_type] = _entity_schema(et.properties)
        array_schema: dict[str, object] = {
            "type": "array",
            "items": {"$ref": f"#/$defs/{et.entity_type}"},
        }
        if et.min > 0:
            array_schema["minItems"] = et.min
        props[et.entity_type] = array_schema

    return {"type": "object", "properties": props, "$defs": defs}


def derive_bindings_schema() -> dict[str, object]:
    """Return the JSON Schema for the top-level ``bindings`` diagram frontmatter field."""
    return BINDINGS_ARRAY_SCHEMA


def _entity_schema(
    properties: tuple[DiagramOwnEntityTypePropertySpec, ...],
) -> dict[str, object]:
    """Schema for one entity type: id (required), label, optional binding shorthand, plus domain properties."""
    required = ["id"] + [p.name for p in properties if p.required]
    all_props: dict[str, object] = {
        "id": {"type": "string"},
        "label": {"type": "string"},
        "binding": BINDING_SHORTHAND_SCHEMA,
        **{p.name: p.schema for p in properties},
    }
    return {"type": "object", "required": required, "properties": all_props}
