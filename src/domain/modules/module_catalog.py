"""Module catalog: immutable registry snapshot and its mutable builder.

``ModuleCatalogBuilder`` gathers ontology and diagram-type modules during
startup; ``.build()`` seals the builder and returns an immutable
``ModuleCatalog``.  Any registration attempt after ``.build()`` raises
``RuntimeError``.
"""

from __future__ import annotations

import functools
import types
from collections.abc import Mapping

from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule, OntologyModule
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, ElementClassInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet


class ModuleCatalogBuilder:
    """Mutable accumulator for ontology and diagram-type modules.

    Build sequence: register modules, then call ``.build()`` exactly once.
    """

    def __init__(self) -> None:
        self._ontologies: dict[str, OntologyModule] = {}
        self._diagram_types: dict[str, DiagramTypeModule] = {}
        self._built = False

    def _check_not_built(self) -> None:
        if self._built:
            raise RuntimeError(
                "ModuleCatalogBuilder has already been built; "
                "register all modules before calling .build()"
            )

    # ── Ontology registration ─────────────────────────────────────────────────

    def register_ontology(self, module: OntologyModule) -> None:
        self._check_not_built()
        if module.name in self._ontologies:
            raise ValueError(f"Ontology '{module.name}' already registered; use replace_ontology")
        self._ontologies[module.name] = module

    def unregister_ontology(self, name: str) -> None:
        self._check_not_built()
        if name not in self._ontologies:
            raise KeyError(name)
        del self._ontologies[name]

    def replace_ontology(self, module: OntologyModule) -> None:
        self._check_not_built()
        self._ontologies[module.name] = module

    # ── Diagram-type registration ─────────────────────────────────────────────

    def register_diagram_type(self, module: DiagramTypeModule) -> None:
        self._check_not_built()
        if module.name in self._diagram_types:
            raise ValueError(
                f"DiagramType '{module.name}' already registered; use replace_diagram_type"
            )
        self._diagram_types[module.name] = module

    def unregister_diagram_type(self, name: str) -> None:
        self._check_not_built()
        if name not in self._diagram_types:
            raise KeyError(name)
        del self._diagram_types[name]

    def replace_diagram_type(self, module: DiagramTypeModule) -> None:
        self._check_not_built()
        self._diagram_types[module.name] = module

    # ── Build ─────────────────────────────────────────────────────────────────

    def build(self) -> ModuleCatalog:
        """Seal this builder and return an immutable ``ModuleCatalog``."""
        self._built = True
        return ModuleCatalog(
            ontologies=dict(self._ontologies),
            diagram_types=dict(self._diagram_types),
        )


class ModuleCatalog:
    """Immutable snapshot of registered ontologies and diagram types.

    Produced by ``ModuleCatalogBuilder.build()``.  All accessors return
    immutable views; cached properties compute aggregates on first access.
    """

    def __init__(
        self,
        ontologies: dict[str, OntologyModule],
        diagram_types: dict[str, DiagramTypeModule],
    ) -> None:
        self._ontologies: Mapping[str, OntologyModule] = types.MappingProxyType(ontologies)
        self._diagram_types: Mapping[str, DiagramTypeModule] = types.MappingProxyType(diagram_types)

    # ── Ontology queries ──────────────────────────────────────────────────────

    def get_ontology(self, name: str) -> OntologyModule:
        try:
            return self._ontologies[name]
        except KeyError:
            raise KeyError(f"No ontology registered with name '{name}'")

    def find_ontology(self, name: str) -> OntologyModule | None:
        return self._ontologies.get(name)

    def all_ontologies(self) -> Mapping[str, OntologyModule]:
        return self._ontologies

    # ── Diagram-type queries ──────────────────────────────────────────────────

    def get_diagram_type(self, name: str) -> DiagramTypeModule:
        try:
            return self._diagram_types[name]
        except KeyError:
            raise KeyError(f"No diagram type registered with name '{name}'")

    def find_diagram_type(self, name: str) -> DiagramTypeModule | None:
        return self._diagram_types.get(name)

    def all_diagram_types(self) -> Mapping[str, DiagramTypeModule]:
        return self._diagram_types

    # ── Aggregated entity / connection queries ────────────────────────────────

    @functools.cached_property
    def _entity_types_map(self) -> Mapping[EntityTypeName, EntityTypeInfo]:
        out: dict[EntityTypeName, EntityTypeInfo] = {}
        for om in self._ontologies.values():
            out.update(om.entity_types)
        return types.MappingProxyType(out)

    @functools.cached_property
    def _connection_types_map(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        out: dict[ConnectionTypeName, ConnectionTypeInfo] = {}
        for om in self._ontologies.values():
            out.update(om.connection_types)
        for dt in self._diagram_types.values():
            out.update(dt.own_connection_types)
        return types.MappingProxyType(out)

    def all_entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]:
        return self._entity_types_map

    def all_connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        return self._connection_types_map

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
        raise KeyError(
            f"Connection type '{name}' not found in any registered ontology or diagram type"
        )

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
        names: set[EntityTypeName] = set()
        for dk in self._diagram_types.values():
            for oe in dk.ui_config.diagram_only_types:
                names.add(EntityTypeName(oe.entity_type))
        return frozenset(names)

    def diagram_entity_types_in_global_search(self) -> frozenset[EntityTypeName]:
        names: set[EntityTypeName] = set()
        for diagram_type in self._diagram_types.values():
            for own_type in diagram_type.ui_config.diagram_only_types:
                if own_type.include_in_global_search:
                    names.add(EntityTypeName(own_type.entity_type))
        return frozenset(names)

    def is_diagram_entity_type(self, name: EntityTypeName) -> bool:
        return name in self.all_diagram_entity_types()

    def all_element_classes(self) -> dict[str, ElementClassInfo]:
        result: dict[str, ElementClassInfo] = {}
        for om in self._ontologies.values():
            for ec_name, info in om.element_classes.items():
                if ec_name in result:
                    raise ValueError(
                        f"Duplicate element class {ec_name!r} declared by multiple ontology modules"
                    )
                result[ec_name] = info
        for dk in self._diagram_types.values():
            for ec_name, info in dk.element_classes.items():
                if ec_name in result:
                    raise ValueError(
                        f"Duplicate element class {ec_name!r} declared by module {dk.name!r} "
                        f"conflicts with an existing declaration"
                    )
                result[ec_name] = info
        return result

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
