"""OntologyModule, DiagramTypeModule, DiagramRenderer protocols."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeAlias, runtime_checkable

from src.domain.concept_scope import ConceptScope
from src.domain.diagrams.diagram_type_config import (
    DiagramOwnEntityTypePropertySpec,
    DiagramOwnEntityTypeUiConfig,
    DiagramRendererReferences,
    DiagramTypeUiConfig,
    DiagramTypeWriteGuidance,
    diagram_type_ui_config_from_mapping,
)
from src.domain.modules.bridges import BridgeDeclaration
from src.domain.modules.module_types import (
    ConnectionTypeName,
    DiagramTypeName,
    ElementClassName,
    EntityTypeName,
    _FreeOntologyType,
)
from src.domain.ontology_representation.behavioral_elements import BehavioralElementDeclaration
from src.domain.ontology_representation.ontology_types import (
    ConnectionTypeInfo,
    ElementClassInfo,
    EntityTypeInfo,
)
from src.domain.ontology_representation.profile_registry import ProfileRegistry
from src.domain.ontology_representation.specializations import SpecializationCatalog
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet
from src.domain.relationships.relationship_derivation_restrictions import DerivationRestriction
from src.domain.relationships.relationship_derivation_rules import CompositionRule

if TYPE_CHECKING:
    from src.domain.diagrams.diagram_verification import (
        DiagramVerificationContribution,
        RepositoryVerificationContribution,
    )
    from src.domain.modules.module_registry import ModuleRegistry
    from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord

# Re-export all diagram_type_config public names for backward-compatible imports.
__all__ = [
    "DiagramOwnEntityTypePropertySpec",
    "DiagramOwnEntityTypeUiConfig",
    "DiagramRendererReferences",
    "DiagramTypeModule",
    "DiagramTypeUiConfig",
    "DiagramTypeWriteGuidance",
    "DiagramRenderer",
    "NativeSvgDiagramRenderer",
    "ModuleClass",
    "OntologyModule",
    "PrimaryOntology",
    "diagram_type_ui_config_from_mapping",
]

PrimaryOntology: TypeAlias = "OntologyModule | _FreeOntologyType"

ModuleClass = Literal["architecture", "assurance"]


@runtime_checkable
class OntologyModule(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def module_class(self) -> ModuleClass: ...

    @property
    def entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]: ...

    @property
    def connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]: ...

    @property
    def permitted_relationships(self) -> PermittedRelationshipSet: ...

    @property
    def derivation_rules(self) -> tuple[CompositionRule, ...]: ...

    @property
    def derivation_restrictions(self) -> tuple[DerivationRestriction, ...]: ...

    @property
    def element_classes(self) -> Mapping[str, ElementClassInfo]: ...

    @property
    def behavioral_elements(self) -> BehavioralElementDeclaration:
        """Which of this ontology's entity types denote something that acts.

        A fact about the ontology's own vocabulary, not about any analysis. Empty is a valid
        answer and means the ontology has not said — see `behavioral_elements`.
        """
        ...

    @property
    def display_section_id(self) -> str: ...

    @property
    def specialization_catalog(self) -> SpecializationCatalog: ...

    @property
    def profile_registry(self) -> ProfileRegistry: ...

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]: ...

    def connection_types_with_class(self, cls: str) -> frozenset[ConnectionTypeName]: ...

    def permits_connection(
        self,
        src: EntityTypeName,
        tgt: EntityTypeName,
        conn: ConnectionTypeName,
    ) -> bool: ...

    def render_display_section(self, artifact_type: str, name: str, alias: str) -> str: ...

    def extract_display_section(self, section_content: str) -> dict | None: ...

    def sprite_for(self, artifact_type: str) -> str | None: ...


@runtime_checkable
class DiagramRenderer(Protocol):
    def render_body(
        self,
        name: str,
        entities: Sequence[EntityRecord],
        connections: Sequence[ConnectionRecord],
        diagram_type: str,
        repo_root: Path,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
    ) -> str: ...

    def inject_includes(self, body: str, repo_root: Path) -> str: ...

    def collect_references(
        self,
        diagram_type: str,
        repo_root: Path,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
        bindings: list[dict[str, object]] | None = None,
    ) -> DiagramRendererReferences: ...


@runtime_checkable
class NativeSvgDiagramRenderer(Protocol):
    """Optional capability for diagram types that own their SVG notation."""

    def render_svg(self, puml_body: str) -> str: ...


@runtime_checkable
class StoreGraphProjectingDiagramType(Protocol):
    """Optional capability for a diagram type drawn from a live graph rather than from an artifact.

    Such a type draws a *sub-graph* of the store behind it: which node types take part, and which
    edges between them are admitted. That is the diagram type's own knowledge — each notation shows
    a different slice of the same graph — so a read surface serving these projections asks the type
    instead of carrying a branch per type.

    Receives the graph the caller is allowed to see and returns the part this diagram draws; both
    lists are already exposure-filtered, and a projection must never widen them.

    Deliberately silent on *which unit of work* inside that store a projection is scoped to. That is
    the projecting module's question and the answer is in the module's own vocabulary, so it is
    declared in the module's own namespace and asked for by the module's own callers — see
    `src.domain.assurance.analysis_scoped_diagram` for how the assurance module states it. A term
    such as an analysis method has no place in this file: any module with a store behind it can
    satisfy this capability, and one that names another module's words excludes the next one.
    """

    def project_store_graph(
        self,
        nodes: Sequence[Mapping[str, object]],
        edges: Sequence[Mapping[str, object]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]: ...


@runtime_checkable
class NodeRepresentingEdgeRenderer(Protocol):
    """Optional capability for diagram types where some drawn edges stand for a *node*.

    A notation may render a node as the arrow between its neighbours rather than as a shape of its
    own — a STAMP control action is the labelled arrow from a controller to what it controls. The
    node still has to be selectable, so a viewer needs to know which drawn edge stands for which
    node. Each entry names the represented node and the endpoints of the edge that draws it.
    """

    def node_representing_edges(
        self,
        *,
        diagram_entities: Mapping[str, object] | None = None,
        diagram_connections: list[dict[str, object]] | None = None,
    ) -> list[dict[str, str]]: ...


@runtime_checkable
class DiagramTypeModule(Protocol):
    @property
    def name(self) -> DiagramTypeName: ...

    @property
    def module_class(self) -> ModuleClass: ...

    @property
    def primary_ontology(self) -> OntologyModule | _FreeOntologyType: ...

    @property
    def element_classes(self) -> Mapping[str, ElementClassInfo]: ...

    def concept_scope(self, registry: ModuleRegistry | None = None) -> ConceptScope: ...
    def accepts_entity_type(self, t: EntityTypeName) -> bool: ...
    def accepts_connection_type(self, t: ConnectionTypeName) -> bool: ...

    def effective_entity_types(
        self, registry: ModuleRegistry | None = None
    ) -> Mapping[EntityTypeName, EntityTypeInfo]: ...
    def effective_connection_types(
        self, registry: ModuleRegistry | None = None
    ) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]: ...

    @property
    def own_entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]: ...

    @property
    def own_connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]: ...

    @property
    def ui_config(self) -> DiagramTypeUiConfig: ...

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet: ...

    @property
    def effective_permitted_relationships(self) -> PermittedRelationshipSet: ...

    @property
    def bridges(self) -> tuple[BridgeDeclaration, ...]: ...

    @property
    def renderer(self) -> DiagramRenderer: ...

    def write_guidance(self) -> DiagramTypeWriteGuidance: ...

    def build_context_extras(
        self,
        repo: Any,
        diagram_id: str,
        diagram_entities: dict[str, Any],
    ) -> dict[str, Any]: ...

    def read_diagram_extras(self, parsed_source: dict[str, Any]) -> dict[str, Any]: ...

    def resolve_diagram_entities(
        self, parsed_source: dict[str, Any], diagram_entities: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    def diagram_verification_contributions(self) -> tuple[DiagramVerificationContribution, ...]: ...

    def repository_verification_contributions(self) -> tuple[RepositoryVerificationContribution, ...]: ...

    def prepare_render_model(self, diagram_entities: dict[str, Any], candidate: Any) -> dict[str, Any]: ...
