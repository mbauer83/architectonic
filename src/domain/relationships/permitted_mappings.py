"""Helpers for resolving diagram-owned mapping specs to concrete model entity types."""

from __future__ import annotations

from collections.abc import Iterable

from src.domain.concept_scope import ConceptScope
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.modules.module_types import ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_protocol import DiagramOwnEntityTypeUiConfig
from src.domain.ontology_representation.ontology_types import PermittedMappingSpec


def resolve_model_entity_types(
    spec: PermittedMappingSpec,
    registry: ModuleRegistry,
) -> frozenset[EntityTypeName]:
    """Return the registered model entity types allowed by one mapping spec."""
    scope = concept_scope_from_mapping_spec(spec, registry)
    return frozenset(scope.admitted_entity_types(dict(registry.all_entity_types())))


def concept_scope_from_mapping_spec(
    spec: PermittedMappingSpec,
    registry: ModuleRegistry,
) -> ConceptScope:
    """Compile permitted_mappings source eligibility into a ConceptScope."""
    result: set[EntityTypeName] = {EntityTypeName(name) for name in spec.entity_types}
    for cls in spec.entity_classes:
        result.update(registry.entity_types_with_class(ElementClassName(cls)))

    for source in spec.sources:
        ontology = registry.find_ontology(source.ontology)
        if ontology is None:
            raise ValueError(f"Unknown ontology in permitted_mappings source: {source.ontology!r}")
        if source.entity_type:
            entity_type = EntityTypeName(source.entity_type)
            if entity_type not in ontology.entity_types:
                raise ValueError(
                    f"Unknown entity type {source.entity_type!r} in ontology {source.ontology!r}"
                )
            result.add(entity_type)
        if source.entity_class:
            result.update(ontology.entity_types_with_class(ElementClassName(source.entity_class)))

    return ConceptScope(entity_types=frozenset(result))


def resolve_model_entity_types_for_diagram_only_types(
    own_types: Iterable[DiagramOwnEntityTypeUiConfig],
    registry: ModuleRegistry,
) -> frozenset[EntityTypeName]:
    """Return the union of all model entity types accepted by diagram-owned entity types."""
    scope = concept_scope_for_diagram_only_types(own_types, registry)
    return frozenset(scope.admitted_entity_types(dict(registry.all_entity_types())))


def concept_scope_for_diagram_only_types(
    own_types: Iterable[DiagramOwnEntityTypeUiConfig],
    registry: ModuleRegistry,
) -> ConceptScope:
    result: set[EntityTypeName] = set()
    for own_type in own_types:
        scope = concept_scope_from_mapping_spec(own_type.permitted_mappings, registry)
        result.update(scope.entity_types or frozenset())
    return ConceptScope(entity_types=frozenset(result))
