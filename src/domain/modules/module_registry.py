"""ModuleRegistry — single authority for all registered ontologies and diagram types."""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule, OntologyModule
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet


class ModuleRegistry:
    def __init__(self) -> None:
        self._ontologies: dict[str, OntologyModule] = {}
        self._diagram_types: dict[str, DiagramTypeModule] = {}

    # ── Registration ─────────────────────────────────────────────────────────

    def register_ontology(self, module: OntologyModule) -> None:
        if module.name in self._ontologies:
            raise ValueError(f"Ontology '{module.name}' already registered; use replace_ontology")
        self._ontologies[module.name] = module

    def unregister_ontology(self, name: str) -> None:
        if name not in self._ontologies:
            raise KeyError(name)
        del self._ontologies[name]

    def replace_ontology(self, module: OntologyModule) -> None:
        self._ontologies[module.name] = module

    def register_diagram_type(self, module: DiagramTypeModule) -> None:
        if module.name in self._diagram_types:
            raise ValueError(f"DiagramType '{module.name}' already registered; use replace_diagram_type")
        self._diagram_types[module.name] = module

    def unregister_diagram_type(self, name: str) -> None:
        if name not in self._diagram_types:
            raise KeyError(name)
        del self._diagram_types[name]

    def replace_diagram_type(self, module: DiagramTypeModule) -> None:
        self._diagram_types[module.name] = module

    # ── Ontology queries ──────────────────────────────────────────────────────

    def get_ontology(self, name: str) -> OntologyModule:
        try:
            return self._ontologies[name]
        except KeyError:
            raise KeyError(f"No ontology registered with name '{name}'")

    def find_ontology(self, name: str) -> OntologyModule | None:
        return self._ontologies.get(name)

    def all_ontologies(self) -> Mapping[str, OntologyModule]:
        return dict(self._ontologies)

    # ── Diagram type queries ──────────────────────────────────────────────────

    def get_diagram_type(self, name: str) -> DiagramTypeModule:
        try:
            return self._diagram_types[name]
        except KeyError:
            raise KeyError(f"No diagram type registered with name '{name}'")

    def find_diagram_type(self, name: str) -> DiagramTypeModule | None:
        return self._diagram_types.get(name)

    def all_diagram_types(self) -> Mapping[str, DiagramTypeModule]:
        return dict(self._diagram_types)

    # ── Aggregated type queries ───────────────────────────────────────────────

    def all_entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]:
        out: dict[EntityTypeName, EntityTypeInfo] = {}
        for om in self._ontologies.values():
            out.update(om.entity_types)
        return out

    def all_connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        out: dict[ConnectionTypeName, ConnectionTypeInfo] = {}
        for om in self._ontologies.values():
            out.update(om.connection_types)
        for dt in self._diagram_types.values():
            out.update(dt.own_connection_types)
        return out

    def get_entity_type(self, name: EntityTypeName) -> EntityTypeInfo:
        for om in self._ontologies.values():
            if name in om.entity_types:
                return om.entity_types[name]
        raise KeyError(f"Entity type '{name}' not found in any registered ontology")

    def find_entity_type(self, name: EntityTypeName) -> EntityTypeInfo | None:
        for om in self._ontologies.values():
            if name in om.entity_types:
                return om.entity_types[name]
        return None

    def get_connection_type(self, name: ConnectionTypeName) -> ConnectionTypeInfo:
        for om in self._ontologies.values():
            if name in om.connection_types:
                return om.connection_types[name]
        for dt in self._diagram_types.values():
            if name in dt.own_connection_types:
                return dt.own_connection_types[name]
        raise KeyError(f"Connection type '{name}' not found in any registered ontology or diagram type")

    def find_connection_type(self, name: ConnectionTypeName) -> ConnectionTypeInfo | None:
        for om in self._ontologies.values():
            if name in om.connection_types:
                return om.connection_types[name]
        for dt in self._diagram_types.values():
            if name in dt.own_connection_types:
                return dt.own_connection_types[name]
        return None

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        result: set[EntityTypeName] = set()
        for om in self._ontologies.values():
            result.update(om.entity_types_with_class(cls))
        return frozenset(result)

    def connection_types_with_class(self, cls: str) -> frozenset[ConnectionTypeName]:
        result: set[ConnectionTypeName] = set()
        for om in self._ontologies.values():
            result.update(om.connection_types_with_class(cls))
        for dt in self._diagram_types.values():
            for ct_name, ct_info in dt.own_connection_types.items():
                if cls in ct_info.classes:
                    result.add(ct_name)
        return frozenset(result)

    def ontology_for_entity_type(self, name: EntityTypeName) -> OntologyModule | None:
        for om in self._ontologies.values():
            if name in om.entity_types:
                return om
        return None

    def aggregated_permitted_relationships(self) -> PermittedRelationshipSet:
        result = PermittedRelationshipSet.empty()
        for om in self._ontologies.values():
            result = result | om.permitted_relationships
        return result

    def all_diagram_entity_types(self) -> frozenset[EntityTypeName]:
        """Return every entity type name that belongs to a diagram type (not the model ontology)."""
        names: set[EntityTypeName] = set()
        for dk in self._diagram_types.values():
            for oe in dk.ui_config.diagram_only_types:
                names.add(EntityTypeName(oe.entity_type))
        return frozenset(names)

    def is_diagram_entity_type(self, name: EntityTypeName) -> bool:
        """Return True if ``name`` is an entity type owned by any registered diagram type."""
        return name in self.all_diagram_entity_types()

    def all_element_classes(self) -> dict[str, ElementClassInfo]:
        """Merge element class declarations from all ontology and diagram type modules.

        Raises ValueError on duplicate class name declared by different sources.
        """
        result: dict[str, ElementClassInfo] = {}
        for om in self._ontologies.values():
            for name, info in om.element_classes.items():
                if name in result:
                    raise ValueError(f"Duplicate element class {name!r} declared by multiple ontology modules")
                result[name] = info
        for dk in self._diagram_types.values():
            for name, info in dk.element_classes.items():
                if name in result:
                    raise ValueError(
                        f"Duplicate element class {name!r} declared by module {dk.name!r} "
                        f"conflicts with an existing declaration"
                    )
                result[name] = info
        return result

    # ── Domain ordering ───────────────────────────────────────────────────────

    def domain_order(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        # An ontology may DECLARE its layer hierarchy (e.g. ArchiMate: motivation above
        # strategy above business/common/application/technology); declared order wins,
        # discovery order only fills in what no ontology declared.
        for om in self._ontologies.values():
            for domain in getattr(om, "domain_order", ()) or ():
                if domain not in seen:
                    seen.add(domain)
                    result.append(domain)
        for om in self._ontologies.values():
            for et in om.entity_types.values():
                domain = et.hierarchy[0] if et.hierarchy else ""
                if not et.internal and domain and domain not in seen:
                    seen.add(domain)
                    result.append(domain)
        return result
