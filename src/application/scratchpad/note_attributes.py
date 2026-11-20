"""A note's attributes, checked as the properties of the entity it would become.

A note may carry attributes from the moment it exists, and below the level where its meta-ontology
attaches a schema they are free: nothing can say what they should be yet. Once the note reaches a
level that carries attributes, the schema of what it has become applies — the same effective schema
an entity of that type and specialization is verified against, resolved by the same owner, and its
values judged by the verifier's own rule. So what the canvas shows about an attribute before a lift
is what the write of the entity would say after it.

Two tiers, as everywhere on this surface. A value the write itself refuses — one that cannot be read
as the type the schema declares — blocks the lift, with the verifier's code. Everything the write
accepts and warns about warns here, and so does an attribute the schema does not declare: it is
carried as an ad-hoc property, which is permitted and worth knowing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from src.application.verification._verifier_rules_schema import stated_property_issues
from src.application.verification.artifact_verifier_types import Severity
from src.domain.ontology_representation.classification_levels import ClassificationLevel
from src.domain.ontology_representation.property_value import encode
from src.domain.scratchpad import Note, NoteFinding, attribute_level_of

#: The effective attribute schema of an element type under the specializations applied to it, or
#: `None` where nothing declares one — which is a free schema, and nothing is checked.
AttributeSchemaSource = Callable[[str, Sequence[str]], Mapping[str, Any] | None]

#: The verifier's code for a property value that cannot be read as its declared type. Used for the
#: one case the verifier never meets, because the entity write fails before it is reached: a value
#: no property cell can hold at all.
_UNREADABLE_VALUE = "E042"


def free_attribute_schema(_element_type: str, _specializations: Sequence[str]) -> None:
    """No type declares a schema. What a caller with no repository to ask is given."""
    return None


def adhoc_attribute_types(attributes: Mapping[str, object]) -> dict[str, str]:
    """The type each attribute's value was written as, where it is not text.

    An entity states the type of an attribute its schema does not declare beside its properties,
    and reads the cell as text when it states none. A note holds typed values, so the statement is
    read off them — which is what lets a number or a list written on a note still be one on the
    entity. A schema-declared attribute ignores it: its type is the schema's.
    """
    return {str(name): kind for name, value in attributes.items() if (kind := _written_as(value))}


def _written_as(value: object) -> str:
    match value:
        case bool():
            return "boolean"
        case int():
            return "integer"
        case float():
            return "number"
        case list():
            return "array"
        case _:
            return ""


def attribute_findings(
    note: Note,
    levels: Sequence[ClassificationLevel],
    schema_of: AttributeSchemaSource,
) -> tuple[NoteFinding, ...]:
    """What the attribute schema says about this note's attributes, or nothing.

    Nothing for a note below every level that carries attributes, for one with no attributes, and
    for one already tied to the model — the entity is the authority on its own properties, and a
    lift does not rewrite it.
    """
    level = attribute_level_of(note, levels)
    if level is None or not note.attributes or not note.element_type or note.model_ref is not None:
        return ()
    # The deepest reached level decides which schema: at the type the type's own, below it the
    # type's merged with the specialization's.
    applied = [note.specialization] if level.source == "specializations" and note.specialization else []
    schema = schema_of(note.element_type, applied)
    if schema is None:
        return ()
    cells, unreadable = _as_cells(note.attributes)
    declared: Mapping[str, Any] = schema.get("properties") or {}
    return (
        *unreadable,
        *(
            NoteFinding(
                message=issue.message, blocks=issue.severity is Severity.ERROR, code=issue.code
            )
            for issue in stated_property_issues(
                cells, schema, artifact_type=note.element_type,
                attribute_types=adhoc_attribute_types(note.attributes), loc="",
            )
        ),
        *(
            NoteFinding(message=(
                f"Attribute '{name}' is not declared for {note.element_type}; it is carried as an "
                "ad-hoc property."
            ))
            for name in sorted(cells) if name not in declared
        ),
    )


def _as_cells(attributes: Mapping[str, object]) -> tuple[dict[str, str], list[NoteFinding]]:
    """Each attribute as the property cell the entity write would store it in.

    Encoded by the property codec, which is what that write does — so the verifier's rule then
    reads exactly what it would read from the written file.
    """
    cells: dict[str, str] = {}
    unreadable: list[NoteFinding] = []
    for name, value in attributes.items():
        try:
            cells[str(name)] = encode(value)  # type: ignore[arg-type]  # refused below if not one
        except TypeError:
            unreadable.append(NoteFinding(
                message=(
                    f"Attribute '{name}' holds a {type(value).__name__}, which no property can: a "
                    "property is text, a number, true or false, or a list of those."
                ),
                blocks=True,
                code=_UNREADABLE_VALUE,
            ))
    return cells, unreadable
