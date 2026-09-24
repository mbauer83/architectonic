"""What a write knows about a diagram's instances, for a renderer that restates them in a kept body."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.domain.icons.resolved_icon import IconSource
from src.domain.ontology_representation.artifact_types import EntityRecord


@dataclass(frozen=True)
class DiagramInstances:
    #: The diagram's own statements about its instances, as its `diagram-entities` holds them.
    diagram_entities: Mapping[str, object]
    #: Every model entity the diagram draws, so a statement about a type reaches each of its instances.
    entity_ids: Sequence[str]
    entity_of: Callable[[str], EntityRecord | None]
    #: How an icon reference becomes a picture; None where the write has no library to ask.
    icon_source: IconSource | None
