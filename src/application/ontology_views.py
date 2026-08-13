"""What the meta-ontology declares, shaped for a client that has to draw or filter with it.

Two reads that were previously answered by hardcoding. A surface needing to colour an element
carried its own palette; a surface needing to know how elements are classified assumed the chain
this meta-ontology happens to declare. Both are the ontology's to answer.

**Ids cross the wire as opaque strings.** A generated union over the level ids `archimate_4`
declares would put its ladder into the frontend contract, and a second meta-ontology declaring its
own would then fail to typecheck rather than reshape the view — the failure the per-module dispatch
exists to prevent. A level is data: an id, a label, and what it governs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from src.domain.ontology_representation.classification_levels import (
    DERIVED_RELATION_LEVELS,
    ClassificationLevel,
)


class DeclaresClassification(Protocol):
    """Just enough of the ontology catalog to answer how things are classified."""

    def classification_levels(self) -> Mapping[str, Sequence[ClassificationLevel]]: ...


class DeclaresAppearance(Protocol):
    """Just enough of it to answer how things are drawn."""

    def domain_appearance(self) -> Mapping[str, Mapping[str, str]]: ...
    def corner_by_entity_type(self) -> Mapping[str, str]: ...
    def de_emphasis_rule(self) -> Mapping[str, str]: ...


def _level(level: ClassificationLevel) -> dict[str, object]:
    return {
        "id": level.id,
        "label": level.label,
        "source": level.source,
        "required": level.required,
        "keys_relationships": level.keys_relationships,
        "narrows_relationships": level.narrows_relationships,
        "carries_attributes": level.carries_attributes,
    }


def classification_levels_payload(
    ontology: DeclaresClassification, *, meta_ontology: str | None = None
) -> dict[str, object]:
    """The ladder for one meta-ontology, keyed by what is being classified.

    Keyed by concept kind rather than served as one list, because a client faceting a graph needs
    the relation side as well as the entity side. The entity ladder is declared per module; the
    relation one is derived today, and this shape keeps working when a module declares its own.
    """
    ladders: Mapping[str, Sequence[ClassificationLevel]] = ontology.classification_levels()
    # Naming no module here on purpose: a meta-ontology's name is its own vocabulary, and a
    # generic view that spells one cannot serve a second. A caller that names none gets the first
    # registered module, which is the deployment's configuration rather than this module's opinion.
    named = meta_ontology or ""
    resolved = named if named in ladders else next(iter(ladders), "")
    entity_levels: Sequence[ClassificationLevel] = ladders.get(resolved) or ()
    return {
        "meta_ontology": resolved,
        "entity": [_level(level) for level in entity_levels],
        "relation": [_level(level) for level in DERIVED_RELATION_LEVELS],
    }


def element_appearance_payload(
    ontology: DeclaresAppearance, *, meta_ontology: str | None = None
) -> dict[str, object]:
    """Colour per domain and corner style per entity type, resolved.

    Corners arrive per type, not per class: resolving the class vocabulary is the ontology's
    business, and a renderer should receive something it can draw.
    """
    appearance = ontology.domain_appearance()
    return {
        "meta_ontology": meta_ontology or "",
        "domain_colors": {domain: values["fill"] for domain, values in appearance.items()},
        "domain_borders": {domain: values["border"] for domain, values in appearance.items()},
        "domain_containers": {domain: values["container"] for domain, values in appearance.items()},
        "corners": dict(ontology.corner_by_entity_type()),
        # The rule, not a second palette: a client muting a colour applies this rather than
        # inventing a grey, which is how the palettes that disagreed came about.
        "de_emphasis": dict(ontology.de_emphasis_rule()),
    }
