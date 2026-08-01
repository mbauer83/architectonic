"""ModuleRegistry — the mutable authority over which ontologies and diagram types are registered.

Registration is this class's job. **Reading is not.** Every query below delegates to a
:class:`ModuleCatalog` built from the current registrations, because the merge rules — which module
wins for a duplicated type, whether diagram-type connection types join the ontologies', what counts
as a domain and in what order — are one set of rules and belong in one place.

They were in two. This class carried its own copy of all twenty-one read methods, twelve of them
byte-identical to the catalog's and the rest differing only in whether the result was memoised or
copied. Nothing held them equal, so "what does the registry answer" and "what does the catalog
answer" were two questions with no guarantee of one answer — and the composition root hands consumers
the catalog while modules and bootstrap ask the registry.

The snapshot is rebuilt on the next read after any registration changes. That is not a cache bolted
on: the catalog memoises its aggregations, so a registry that recomputed per call was doing the work
again on every question, and one that kept a stale snapshot would answer from before a hot-reload.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule, OntologyModule
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet


class ModuleRegistry:
    def __init__(self) -> None:
        self._ontologies: dict[str, OntologyModule] = {}
        self._diagram_types: dict[str, DiagramTypeModule] = {}
        self._snapshot: ModuleCatalog | None = None

    @property
    def catalog(self) -> ModuleCatalog:
        """A frozen view of what is registered now, and the answer to every query below.

        Public because the composition root needs exactly this — the point at which the mutable
        registration phase ends and the immutable read phase begins — and reaching through
        ``_ontologies`` to build one by hand is how a second set of merge rules gets written.
        """
        if self._snapshot is None:
            self._snapshot = ModuleCatalog(dict(self._ontologies), dict(self._diagram_types))
        return self._snapshot

    def _registrations_changed(self) -> None:
        self._snapshot = None

    # ── Registration ─────────────────────────────────────────────────────────

    def register_ontology(self, module: OntologyModule) -> None:
        if module.name in self._ontologies:
            raise ValueError(f"Ontology '{module.name}' already registered; use replace_ontology")
        self._ontologies[module.name] = module
        self._registrations_changed()

    def unregister_ontology(self, name: str) -> None:
        if name not in self._ontologies:
            raise KeyError(name)
        del self._ontologies[name]
        self._registrations_changed()

    def replace_ontology(self, module: OntologyModule) -> None:
        self._ontologies[module.name] = module
        self._registrations_changed()

    def register_diagram_type(self, module: DiagramTypeModule) -> None:
        if module.name in self._diagram_types:
            raise ValueError(f"DiagramType '{module.name}' already registered; use replace_diagram_type")
        self._diagram_types[module.name] = module
        self._registrations_changed()

    def unregister_diagram_type(self, name: str) -> None:
        if name not in self._diagram_types:
            raise KeyError(name)
        del self._diagram_types[name]
        self._registrations_changed()

    def replace_diagram_type(self, module: DiagramTypeModule) -> None:
        self._diagram_types[module.name] = module
        self._registrations_changed()

    # ── Queries, every one of them the catalog's ──────────────────────────────

    def get_ontology(self, name: str) -> OntologyModule:
        return self.catalog.get_ontology(name)

    def find_ontology(self, name: str) -> OntologyModule | None:
        return self.catalog.find_ontology(name)

    def all_ontologies(self) -> Mapping[str, OntologyModule]:
        return self.catalog.all_ontologies()

    def get_diagram_type(self, name: str) -> DiagramTypeModule:
        return self.catalog.get_diagram_type(name)

    def find_diagram_type(self, name: str) -> DiagramTypeModule | None:
        return self.catalog.find_diagram_type(name)

    def all_diagram_types(self) -> Mapping[str, DiagramTypeModule]:
        return self.catalog.all_diagram_types()

    def all_entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]:
        return self.catalog.all_entity_types()

    def all_connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        return self.catalog.all_connection_types()

    def get_entity_type(self, name: EntityTypeName) -> EntityTypeInfo:
        return self.catalog.get_entity_type(name)

    def find_entity_type(self, name: EntityTypeName) -> EntityTypeInfo | None:
        return self.catalog.find_entity_type(name)

    def get_connection_type(self, name: ConnectionTypeName) -> ConnectionTypeInfo:
        return self.catalog.get_connection_type(name)

    def find_connection_type(self, name: ConnectionTypeName) -> ConnectionTypeInfo | None:
        return self.catalog.find_connection_type(name)

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        return self.catalog.entity_types_with_class(cls)

    def connection_types_with_class(self, cls: str) -> frozenset[ConnectionTypeName]:
        return self.catalog.connection_types_with_class(cls)

    def ontology_for_entity_type(self, name: EntityTypeName) -> OntologyModule | None:
        return self.catalog.ontology_for_entity_type(name)

    def aggregated_permitted_relationships(self) -> PermittedRelationshipSet:
        return self.catalog.aggregated_permitted_relationships()

    def all_diagram_entity_types(self) -> frozenset[EntityTypeName]:
        return self.catalog.all_diagram_entity_types()

    def is_diagram_entity_type(self, name: EntityTypeName) -> bool:
        return self.catalog.is_diagram_entity_type(name)

    def diagram_entity_types_in_global_search(self) -> frozenset[EntityTypeName]:
        return self.catalog.diagram_entity_types_in_global_search()

    def all_element_classes(self) -> dict[str, ElementClassInfo]:
        return self.catalog.all_element_classes()

    def domain_order(self) -> list[str]:
        return self.catalog.domain_order()
