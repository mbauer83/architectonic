"""What the ArchiMate renderer states about one element of a body kept as written.

A kept body is re-pictured in place (`archimate_instance_icons.restate_instance_icons`); these are the
two statements that needs from the renderer: the glyph an element shows when no icon stands in for
it, and its whole declaration when it changes kind — becoming a figure, or ceasing to be one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.infrastructure.rendering.archimate_entity_declarations import entity_declaration, type_glyph
from src.infrastructure.rendering.archimate_instance_icons import DrawnIcon
from src.infrastructure.rendering.archimate_occurrences import display_label_overrides, instance_id_of


class ArchimateKeptDeclarations:
    def __init__(
        self,
        registry: Any,
        junction_types: frozenset[str],
        specializations: SpecializationCatalog,
        diagram_entities: Mapping[str, object],
    ) -> None:
        self._registry = registry
        self._junction_types = junction_types
        self._specializations = specializations
        self._labels = display_label_overrides(diagram_entities)

    def glyph(self, entity: EntityRecord) -> str:
        return type_glyph(entity, self._registry, self._specializations)

    def declaration(self, entity: EntityRecord, alias: str, icon: DrawnIcon | None) -> str:
        """The declaration the renderer would write, with the label this diagram gives the instance."""
        return entity_declaration(
            entity, alias, self._registry, self._junction_types, self._specializations,
            instance_label=self._labels.get(instance_id_of(entity)), instance_icon=icon,
        )
