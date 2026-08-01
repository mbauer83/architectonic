"""One diagram type's UI config as a wire payload.

``dataclasses.asdict`` was doing this job and it was the wrong tool: it walks private fields too, so
``PermittedRelationshipSet``'s single ``_rules`` attribute reached the wire as
``permitted_connections: {"_rules": [...]}``. A private attribute name had become part of an HTTP
contract, and renaming it inside the domain would have broken every consumer of the route.

Written by hand rather than by a generic serialiser, because that is what makes the two disagreements
visible: the relationship set is projected through its public ``rules()``, and a frozenset becomes a
sorted list so the payload does not reshuffle between processes.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.domain.diagrams.diagram_type_config import (
    DiagramOwnEntityTypeUiConfig,
    DiagramTypeUiConfig,
)


def ui_config_payload(config: DiagramTypeUiConfig) -> dict[str, Any]:
    """The config as the route serves it."""
    return {
        "label": config.label,
        "description": config.description,
        "entity_search_filter": config.entity_search_filter,
        "diagram_only_types": [_own_type(entry) for entry in config.diagram_only_types],
        "type_ui_slots": dict(config.type_ui_slots),
        "primitive_types": list(config.primitive_types),
    }


def _own_type(entry: DiagramOwnEntityTypeUiConfig) -> dict[str, Any]:
    return {
        "entity_type": entry.entity_type,
        "label": entry.label,
        "plural": entry.plural,
        "min": entry.min,
        "max": entry.max,
        "permitted_mappings": asdict(entry.permitted_mappings),
        "mapping_required": entry.mapping_required,
        "classes": list(entry.classes),
        "create_when": entry.create_when,
        "never_create_when": entry.never_create_when,
        "properties": [asdict(spec) for spec in entry.properties],
        # The public reading, not the dataclass's private field.
        "permitted_connections": [asdict(rule) for rule in entry.permitted_connections.rules()],
        "required_connections": [asdict(rc) for rc in entry.required_connections],
        "managed_fields": (
            None if entry.managed_fields is None
            else [list(pair) for pair in entry.managed_fields]
        ),
        # Kept explicitly: an earlier hand-written version of this builder omitted it, and the
        # type-level contract assertion is what caught the field going missing from the wire.
        "editable_metadata": asdict(entry.editable_metadata),
        "identity_scope": entry.identity_scope,
        "id_prefix": entry.id_prefix,
        "include_in_global_search": entry.include_in_global_search,
    }
