"""DiagramTypeBase mixin providing default DiagramTypeModule implementations."""

from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from src.domain.concept_scope import ConceptScope
from src.domain.diagrams.diagram_type_config import (
    DiagramTypeUiConfig,
    DiagramTypeWriteGuidance,
    diagram_type_ui_config_from_mapping,
)
from src.domain.modules.bridges import BridgeDeclaration
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName, _FreeOntologyType
from src.domain.ontology_representation.ontology_protocol import ModuleClass, OntologyModule
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

if TYPE_CHECKING:
    from src.domain.modules.module_registry import ModuleRegistry


class DiagramTypeBase:
    """Mixin providing default DiagramTypeModule implementations.

    Subclasses must provide: name, primary_ontology, own_entity_types,
    own_connection_types, own_permitted_relationships, and _config. They may
    override concept_scope when the default scope derived from ownership is not
    expressive enough.
    """

    module_class: ModuleClass = "architecture"

    @property
    def bridges(self) -> tuple[BridgeDeclaration, ...]:
        return ()

    @property
    def element_classes(self) -> Mapping[str, ElementClassInfo]:
        return {}

    def concept_scope(self, registry: ModuleRegistry | None = None) -> ConceptScope:
        del registry
        configured = getattr(self, "_concept_scope", None)
        if isinstance(configured, ConceptScope):
            return configured
        if isinstance(self.primary_ontology, _FreeOntologyType):  # type: ignore[attr-defined]
            return ConceptScope(
                entity_types=frozenset(self.own_entity_types),  # type: ignore[attr-defined]
                connection_types=frozenset(self.own_connection_types),  # type: ignore[attr-defined]
            )
        ontology: OntologyModule = self.primary_ontology  # type: ignore[assignment]
        return ConceptScope(connection_types=frozenset(ontology.connection_types))

    def accepts_entity_type(self, t: EntityTypeName) -> bool:
        if isinstance(self.primary_ontology, _FreeOntologyType):  # type: ignore[attr-defined]
            info = self.own_entity_types.get(t)  # type: ignore[attr-defined]
            return self.concept_scope().admits_entity_type(t, info)
        ontology: OntologyModule = self.primary_ontology  # type: ignore[assignment]
        info = ontology.entity_types.get(t)
        return info is not None and self.concept_scope().admits_entity_type(t, info)

    def accepts_connection_type(self, t: ConnectionTypeName) -> bool:
        return self.concept_scope().admits_connection_type(t)

    @property
    def effective_permitted_relationships(self) -> PermittedRelationshipSet:
        diagram_conn_rules = PermittedRelationshipSet.empty()
        for oe in self.ui_config.diagram_only_types:  # type: ignore[attr-defined]
            diagram_conn_rules = diagram_conn_rules | oe.permitted_connections

        if isinstance(self.primary_ontology, _FreeOntologyType):  # type: ignore[attr-defined]
            return self.own_permitted_relationships | diagram_conn_rules  # type: ignore[attr-defined]
        ontology: OntologyModule = self.primary_ontology  # type: ignore[assignment]
        accepted_base_entities = frozenset(
            t
            for t in ontology.entity_types
            if self.accepts_entity_type(t)  # type: ignore[attr-defined]
        )
        accepted_base_conns = frozenset(
            t
            for t in ontology.connection_types
            if self.accepts_connection_type(t)  # type: ignore[attr-defined]
        )
        inherited = ontology.permitted_relationships.filter_to(
            accepted_base_entities,
            accepted_base_conns,
        )
        return inherited | self.own_permitted_relationships | diagram_conn_rules  # type: ignore[attr-defined]

    def effective_entity_types(self, registry: ModuleRegistry | None = None) -> Mapping[EntityTypeName, EntityTypeInfo]:
        scope = self.concept_scope(registry)
        if isinstance(self.primary_ontology, _FreeOntologyType):  # type: ignore[attr-defined]
            candidates = dict(self.own_entity_types)  # type: ignore[attr-defined]
            if scope.entity_types is None or scope.entity_types:
                candidates.update(_resolve_registry(registry).all_entity_types())
            return scope.admitted_entity_types(candidates)
        ontology: OntologyModule = self.primary_ontology  # type: ignore[assignment]
        out = scope.admitted_entity_types(dict(ontology.entity_types))
        out.update(self.own_entity_types)  # type: ignore[attr-defined]
        return out

    def effective_connection_types(
        self, registry: ModuleRegistry | None = None
    ) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        scope = self.concept_scope(registry)
        if isinstance(self.primary_ontology, _FreeOntologyType):  # type: ignore[attr-defined]
            candidates = dict(self.own_connection_types)  # type: ignore[attr-defined]
            if scope.connection_types is None or scope.connection_types:
                candidates.update(_resolve_registry(registry).all_connection_types())
            return scope.admitted_connection_types(candidates)
        ontology: OntologyModule = self.primary_ontology  # type: ignore[assignment]
        out = scope.admitted_connection_types(dict(ontology.connection_types))
        out.update(self.own_connection_types)  # type: ignore[attr-defined]
        return out

    @functools.cached_property
    def ui_config(self) -> DiagramTypeUiConfig:
        """How this type presents itself, taken from the `ui:` block of its own `config.yaml`.

        A subclass that has to assemble its configuration from more than one source sets `_ui_config`
        in `__init__` and that wins; every other type is served from `_config` here rather than
        wiring up the same call itself. Reading it in one place is what makes the `ui:` contract
        real: while this defaulted to a title-cased type name, five types declared a label and
        description their config was never asked for, and shipped "Gsn" and "Uca Matrix" instead.
        """
        configured = getattr(self, "_ui_config", None)
        if isinstance(configured, DiagramTypeUiConfig):
            return configured
        default_label = str(self.name).replace("-", " ").title()  # type: ignore[attr-defined]
        config = getattr(self, "_config", None)
        if isinstance(config, Mapping):
            return diagram_type_ui_config_from_mapping(config, default_label=default_label)
        return DiagramTypeUiConfig(label=default_label, entity_search_filter=True)

    def write_guidance(self) -> DiagramTypeWriteGuidance:
        return DiagramTypeWriteGuidance(when_to_use="", when_not_to_use="")

    def build_context_extras(
        self,
        repo: Any,
        diagram_id: str,
        diagram_entities: dict[str, Any],
    ) -> dict[str, Any]:
        return {}

    def read_diagram_extras(self, parsed_source: dict[str, Any]) -> dict[str, Any]:
        return {}

    def diagram_verification_contributions(self) -> tuple:
        return ()

    def repository_verification_contributions(self) -> tuple:
        return ()

    def prepare_render_model(
        self, diagram_entities: dict[str, Any], candidate: Any = None
    ) -> dict[str, Any]:
        return diagram_entities


def _resolve_registry(registry: ModuleRegistry | None) -> ModuleRegistry:
    if registry is not None:
        return registry
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()
