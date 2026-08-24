"""Domain metadata types for entity and connection ontologies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from src.domain.ontology_representation.relation_notation import (
    DEFAULT_NOTATION,
    RelationNotation,
)


@dataclass(frozen=True)
class ElementClassInfo:
    """Declaration of an element class (meta-type) used in element_classes lists."""

    name: str
    description: str = ""


@dataclass(frozen=True)
class RequiredConnection:
    """Mandatory connection that an entity type must always have to a host entity."""

    connection_type: str  # ConnectionTypeName
    target: str  # entity type name or "@class-name"; never "_diagram"
    cardinality_min: int = 1
    cardinality_max: int | None = None  # None = unbounded


@dataclass(frozen=True)
class MappingSourceSpec:
    """One model-side source that a diagram-owned entity type may map from."""

    ontology: str
    entity_type: str | None = None
    entity_class: str | None = None
    transparent: bool = False

    def as_config(self) -> dict[str, Any]:
        """This source in the configuration form :func:`mapping_spec_from_config` reads back.

        The round trip is the point, and ``test_ontology_types.py`` holds it: this is not "a dict of
        the fields" but the *external representation* of this type, which the parser above already
        owned one direction of. Five call sites had spelled it out by hand — four diagram-type
        modules and the write boundary's guidance serialiser — and a field added here would have
        reached the wire from none of them.
        """
        return {
            "ontology": self.ontology,
            "entity_type": self.entity_type,
            "entity_class": self.entity_class,
            "transparent": self.transparent,
        }


@dataclass(frozen=True)
class PermittedMappingSpec:
    """Which model entities a diagram-owned entity may reference."""

    entity_types: tuple[str, ...] = ()
    entity_classes: tuple[str, ...] = ()
    sources: tuple[MappingSourceSpec, ...] = ()

    def has_any(self) -> bool:
        return bool(self.entity_types or self.entity_classes or self.sources)

    def as_config(self) -> dict[str, Any]:
        """This spec in the configuration form :func:`mapping_spec_from_config` reads back.

        ``sources`` is omitted when empty rather than written as ``[]``: the key's absence is what a
        spec with no ontology sources has always looked like on the wire, and emitting an empty list
        would change the payload of every diagram type that declares plain types and classes.
        """
        config: dict[str, Any] = {
            "entity_types": list(self.entity_types),
            "entity_classes": list(self.entity_classes),
        }
        if self.sources:
            config["sources"] = [source.as_config() for source in self.sources]
        return config


def mapping_spec_from_config(raw: object) -> PermittedMappingSpec:
    """Parse a mapping spec from YAML/JSON-like configuration data."""
    cfg: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    return PermittedMappingSpec(
        entity_types=tuple(str(v) for v in cfg.get("entity_types", ())),
        entity_classes=tuple(str(v) for v in cfg.get("entity_classes", ())),
        sources=tuple(
            _mapping_source_from_config(item)
            for item in cfg.get("sources", ())
            if isinstance(item, Mapping)
        ),
    )


def _mapping_source_from_config(raw: Mapping[str, Any]) -> MappingSourceSpec:
    return MappingSourceSpec(
        ontology=str(raw["ontology"]),
        entity_type=str(raw["entity_type"]) if raw.get("entity_type") else None,
        entity_class=str(raw["entity_class"]) if raw.get("entity_class") else None,
        transparent=bool(raw.get("transparent", False)),
    )


@dataclass(frozen=True)
class EntityTypeInfo:
    """Canonical metadata for a single entity type.

    ``hierarchy`` is the full path from ``model/`` to the type-specific directory,
    e.g. ``("motivation", "stakeholder")``.  ``hierarchy[0]`` is the domain (layer)
    used for grouping and filtering; ``hierarchy[-1]`` is the type-specific leaf
    directory.  The loader derives the leaf from ``artifact_type`` so YAML only
    needs to specify the domain-level segments.
    """

    artifact_type: str
    prefix: str
    hierarchy: tuple[str, ...]
    classes: tuple[str, ...]
    create_when: str
    never_create_when: str
    internal: bool = False
    required_connections: tuple[RequiredConnection, ...] = ()
    min: int = 0
    max: int | None = None
    permitted_mappings: PermittedMappingSpec = field(default_factory=PermittedMappingSpec)
    mapping_required: bool = False
    identity_scope: Literal["diagram", "workspace"] = "diagram"
    id_prefix: str | None = None


#: The kinds of relation an ontology may declare — schema vocabulary, shared by ArchiMate 4 and the
#: datatype notation, as against the type names each module owns. Kept a set of strings rather than a
#: `Literal` because every value arrives from a YAML file: narrowing the field would buy type-level
#: safety only by forcing each loader to suppress the checker, and nothing branches over the set.
RELATIONSHIP_KINDS: frozenset[str] = frozenset({"association", "containment", "generalization", "dependency"})

#: One element is part of another — composition and aggregation carry it in ArchiMate 4,
#: `dt-composition` and `dt-aggregation` in the datatype notation. Named so a generic reader can ask
#: "which relations contain?" without spelling any ontology's type names.
CONTAINMENT_KIND = "containment"


@dataclass(frozen=True)
class ConnectionTypeInfo:
    """Canonical metadata for a single connection type.

    ``create_when``/``never_create_when`` mirror the entity-type slots: authoring guidance for the
    relationship itself, empty in the shipped module and populated from the imported guidance
    overlay, so a relationship type is as answerable as an element type in every guidance surface.
    """

    artifact_type: str
    conn_lang: str
    create_when: str = ""
    never_create_when: str = ""
    archimate_relationship_type: str | None = None
    symmetric: bool = False
    puml_arrow: str = "-->"
    #: How the relationship is DRAWN. Separate from `puml_arrow`, which is the PlantUML
    #: spelling and loses the distinction between composition and aggregation; see
    #: `relation_notation`.
    notation: RelationNotation = DEFAULT_NOTATION
    show_stereotype: bool = True
    classes: tuple[str, ...] = ()
    hierarchy_priority: int | None = None
    hierarchy_label: str | None = None
    bidirectional_sync: bool = False
    embedding: Literal["none", "array", "property"] = "none"
    embed_key: str | None = None
    cascade_delete_source: bool = False
    #: What sort of relation this is, from `RELATIONSHIP_KINDS`. Schema vocabulary rather than any
    #: one ontology's type names, which is what lets a generic reader ask "which relations contain?"
    #: without spelling `archimate-composition`.
    relationship_kind: str | None = None
    #: Whether a target may be claimed by at most one source of this relation. Declared here rather
    #: than inferred, because `relationship_kind` cannot carry it: composition and aggregation are
    #: both `containment` and exclusivity is the whole of what separates them — a part belongs to one
    #: whole or it is aggregated. A generic rule can then ask "may two sources claim this target?"
    #: without spelling any ontology's type names.
    exclusive_target: bool = False
    derivation_role: Literal["structural", "dependency", "dynamic", "specialization"] | None = None
    derivation_strength: int | None = None
