"""Protocol compliance tests for all registered OntologyModule and DiagramTypeModule instances.

Verifies that every module registered at startup satisfies the declared protocols
and upholds their structural contracts.
"""

from __future__ import annotations

import pytest

from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule, OntologyModule
from src.infrastructure.app_bootstrap import build_module_registry


@pytest.fixture(scope="module")
def registry():
    return build_module_registry()


# ── OntologyModule compliance ─────────────────────────────────────────────────


class TestOntologyModuleProtocol:
    def test_all_ontologies_are_isinstance(self, registry) -> None:
        for name, module in registry.all_ontologies().items():
            assert isinstance(module, OntologyModule), f"Ontology {name!r} does not satisfy OntologyModule protocol"

    def test_entity_type_names_are_strings(self, registry) -> None:
        for name, module in registry.all_ontologies().items():
            for type_name in module.entity_types:
                assert isinstance(type_name, str), f"Ontology {name!r}: entity type key {type_name!r} is not a str"

    def test_connection_type_names_are_strings(self, registry) -> None:
        for name, module in registry.all_ontologies().items():
            for type_name in module.connection_types:
                assert isinstance(type_name, str), f"Ontology {name!r}: connection type key {type_name!r} is not a str"

    def test_permitted_relationships_entity_refs_in_vocabulary(self, registry) -> None:
        """All entity type names in permitted_relationships exist in the ontology's entity vocabulary."""
        for name, module in registry.all_ontologies().items():
            known_types = set(module.entity_types.keys())
            for rel in module.permitted_relationships._rules:
                for type_ref in (rel.source_type, rel.target_type):
                    assert type_ref in known_types, (
                        f"Ontology {name!r}: permitted relationship references unknown entity type {type_ref!r}"
                    )

    def test_permitted_relationships_conn_refs_in_vocabulary(self, registry) -> None:
        """All connection type names in permitted_relationships exist in the ontology's connection vocabulary."""
        for name, module in registry.all_ontologies().items():
            known_types = set(module.connection_types.keys())
            for rel in module.permitted_relationships._rules:
                assert rel.connection_type in known_types, (
                    f"Ontology {name!r}: permitted relationship references "
                    f"unknown connection type {rel.connection_type!r}"
                )

    def test_entity_types_with_class_subset_of_entity_types(self, registry) -> None:
        from src.domain.modules.module_types import ElementClassName

        for name, module in registry.all_ontologies().items():
            all_types = set(module.entity_types.keys())
            internal = module.entity_types_with_class(ElementClassName("internal"))
            assert internal.issubset(all_types), f"Ontology {name!r}: internal class types not a subset of entity_types"


# ── DiagramTypeModule compliance ──────────────────────────────────────────────


class TestDiagramTypeModuleProtocol:
    def test_all_diagram_types_are_isinstance(self, registry) -> None:
        for name, module in registry.all_diagram_types().items():
            assert isinstance(module, DiagramTypeModule), (
                f"DiagramType {name!r} does not satisfy DiagramTypeModule protocol"
            )

    def test_activity_diagram_kind_is_registered(self, registry) -> None:
        activity = registry.find_diagram_type("activity")

        assert activity is not None
        assert isinstance(activity, DiagramTypeModule)
        assert activity.ui_config.diagram_only_types[0].entity_type == "swimlane"

    def test_name_matches_registry_key(self, registry) -> None:
        for key, module in registry.all_diagram_types().items():
            assert module.name == key, f"DiagramType key {key!r} does not match module.name {module.name!r}"

    def test_effective_entity_types_subset_of_registry(self, registry) -> None:
        all_entity_types = set(registry.all_entity_types().keys())
        for name, module in registry.all_diagram_types().items():
            for type_name in module.effective_entity_types(registry):
                assert type_name in all_entity_types, (
                    f"DiagramType {name!r}: effective entity type {type_name!r} not in registry"
                )

    def test_effective_connection_types_subset_of_registry(self, registry) -> None:
        all_conn_types = set(registry.all_connection_types().keys())
        for name, module in registry.all_diagram_types().items():
            for type_name in module.effective_connection_types(registry):
                assert type_name in all_conn_types, (
                    f"DiagramType {name!r}: effective connection type {type_name!r} not in registry"
                )

    def test_accepts_entity_type_consistent_with_effective(self, registry) -> None:
        for name, module in registry.all_diagram_types().items():
            effective = set(module.effective_entity_types().keys())
            for t in effective:
                assert module.accepts_entity_type(EntityTypeName(t)), (
                    f"DiagramType {name!r}: accepts_entity_type({t!r}) returns False "
                    f"but {t!r} is in effective_entity_types()"
                )

    def test_accepts_connection_type_consistent_with_effective(self, registry) -> None:
        for name, module in registry.all_diagram_types().items():
            effective = set(module.effective_connection_types().keys())
            for t in effective:
                assert module.accepts_connection_type(ConnectionTypeName(t)), (
                    f"DiagramType {name!r}: accepts_connection_type({t!r}) returns False "
                    f"but {t!r} is in effective_connection_types()"
                )
