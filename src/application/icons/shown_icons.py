"""Which icon each instance of a diagram shows, for an editor: the answer the renderer draws, before it draws.

An editor names its instances — an entity's id for its base drawing, an occurrence's id with the entity
it draws, a hosted node's own id — so this needs no notation's help to find them: an instance is
classified by its entity through the model, or by the `diagram-entities` list that hosts it. Where the
notation draws a model entity as a type of its own (a C4 container), the diagram type's projection says
which, and the caller passes that answer in; the editor never names it. The precedence is
`effective_icons`', so what the editor shows and what the body draws cannot differ.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from src.application.icons.effective_icons import (
    EffectiveIcon,
    effective_icon,
    icon_assignments,
    specialization_defaults,
)
from src.application.icons.icon_usage import hosted_type_of
from src.domain.icons.element_names import names_most_specific_first
from src.domain.icons.resolved_icon import IconSource
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.ontology_representation.specializations import SpecializationCatalog


@dataclass(frozen=True, slots=True)
class EditedInstance:
    instance_id: str
    #: The entity it draws, where that is not the instance id itself (an occurrence).
    entity_id: str | None = None


def shown_icons(
    diagram_entities: Mapping[str, object],
    instances: Sequence[EditedInstance],
    entity_of: Callable[[str], EntityRecord | None],
    source: IconSource,
    specializations: SpecializationCatalog,
    drawn_as: Mapping[str, str] | None = None,
) -> dict[str, EffectiveIcon]:
    """instance id → the icon it shows; an instance showing its type glyph is absent.

    *drawn_as* is entity id → the type the notation draws it as, from the diagram type's projection.
    """
    drawn = drawn_as or {}
    assignments = icon_assignments(diagram_entities)
    shown: dict[str, EffectiveIcon] = {}
    for instance in instances:
        entity_id = instance.entity_id or instance.instance_id
        entity = entity_of(entity_id)
        if entity is not None:
            names = names_most_specific_first(entity.artifact_type, entity.specializations, drawn.get(entity_id))
            default = specialization_defaults(entity.artifact_type, specializations)
            icon = effective_icon(instance.instance_id, names, assignments, source, default)
        elif (hosted := hosted_type_of(instance.instance_id, diagram_entities)) is not None:
            icon = effective_icon(instance.instance_id, (hosted,), assignments, source)
        else:
            icon = None
        if icon is not None:
            shown[instance.instance_id] = icon
    return shown
