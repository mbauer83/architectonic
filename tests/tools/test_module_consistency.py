"""Registry consistency: all registered modules have internally coherent permitted_relationships."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from src.application.startup_validation import RegistryConsistencyError, validate_registry_consistency
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationship, PermittedRelationshipSet

# ── Stubs ─────────────────────────────────────────────────────────────────────


def _entity_type(name: str) -> EntityTypeInfo:
    return EntityTypeInfo(
        artifact_type=name, prefix=name[:3].upper(), hierarchy=(name,), classes=(), create_when="", never_create_when=""
    )


def _conn_type(name: str) -> ConnectionTypeInfo:
    return ConnectionTypeInfo(artifact_type=name, conn_lang="test", classes=())


def _prs(*triples: tuple[str, str, str]) -> PermittedRelationshipSet:
    return PermittedRelationshipSet(frozenset(
        PermittedRelationship(EntityTypeName(s), EntityTypeName(t), ConnectionTypeName(c))
        for s, t, c in triples
    ))


class _StubOntology:
    def __init__(
        self,
        name: str,
        entity_names: list[str],
        conn_names: list[str],
        permitted: PermittedRelationshipSet = PermittedRelationshipSet.empty(),
    ) -> None:
        self._name = name
        self._entity_types: dict[EntityTypeName, EntityTypeInfo] = {
            EntityTypeName(n): _entity_type(n) for n in entity_names
        }
        self._connection_types: dict[ConnectionTypeName, ConnectionTypeInfo] = {
            ConnectionTypeName(n): _conn_type(n) for n in conn_names
        }
        self._permitted = permitted

    @property
    def name(self) -> str:
        return self._name

    @property
    def entity_types(self) -> Mapping[EntityTypeName, EntityTypeInfo]:
        return self._entity_types

    @property
    def connection_types(self) -> Mapping[ConnectionTypeName, ConnectionTypeInfo]:
        return self._connection_types

    @property
    def permitted_relationships(self) -> PermittedRelationshipSet:
        return self._permitted

    @property
    def element_classes(self) -> Mapping[str, Any]:
        return {}

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        return frozenset()

    def connection_types_with_class(self, cls: str) -> frozenset[ConnectionTypeName]:
        return frozenset()


def _registry_with(*ontologies: _StubOntology) -> ModuleRegistry:
    r = ModuleRegistry()
    for om in ontologies:
        r.register_ontology(om)
    return r


# ── Happy-path: all registered modules are currently consistent ───────────────


def test_all_registered_modules_are_internally_consistent() -> None:
    """build_module_registry() must not raise — proves current state is drift-free.

    This calls validate_registry_consistency internally, covering both the archimate_4
    ontology (full entity + connection type check) and all diagram types (entity type
    check against diagram_only_types).
    """
    from src.infrastructure.app_bootstrap import build_module_registry
    build_module_registry()  # raises RegistryConsistencyError on any drift


# ── Ontology module drift detection ──────────────────────────────────────────


def test_dangling_source_entity_in_ontology_permitted_relationships() -> None:
    om = _StubOntology(
        "test-ont",
        entity_names=["real-entity"],
        conn_names=["real-conn"],
        permitted=_prs(("ghost-entity", "real-entity", "real-conn")),
    )
    with pytest.raises(RegistryConsistencyError) as exc_info:
        validate_registry_consistency(_registry_with(om))
    assert any("ghost-entity" in e and "source" in e for e in exc_info.value.errors)


def test_dangling_target_entity_in_ontology_permitted_relationships() -> None:
    om = _StubOntology(
        "test-ont",
        entity_names=["real-entity"],
        conn_names=["real-conn"],
        permitted=_prs(("real-entity", "ghost-entity", "real-conn")),
    )
    with pytest.raises(RegistryConsistencyError) as exc_info:
        validate_registry_consistency(_registry_with(om))
    assert any("ghost-entity" in e and "target" in e for e in exc_info.value.errors)


def test_dangling_connection_in_ontology_permitted_relationships() -> None:
    om = _StubOntology(
        "test-ont",
        entity_names=["real-entity"],
        conn_names=["real-conn"],
        permitted=_prs(("real-entity", "real-entity", "ghost-conn")),
    )
    with pytest.raises(RegistryConsistencyError) as exc_info:
        validate_registry_consistency(_registry_with(om))
    assert any("ghost-conn" in e and "connection" in e for e in exc_info.value.errors)


def test_valid_ontology_permitted_relationships_passes() -> None:
    om = _StubOntology(
        "test-ont",
        entity_names=["actor", "system"],
        conn_names=["uses"],
        permitted=_prs(("actor", "system", "uses"), ("system", "system", "uses")),
    )
    validate_registry_consistency(_registry_with(om))  # must not raise


def test_duplicate_errors_are_reported_once() -> None:
    # ghost-entity appears as source in two rules — should produce exactly one error message
    om = _StubOntology(
        "test-ont",
        entity_names=["real-entity"],
        conn_names=["real-conn"],
        permitted=_prs(
            ("ghost-entity", "real-entity", "real-conn"),
            ("ghost-entity", "real-entity", "real-conn"),
        ),
    )
    with pytest.raises(RegistryConsistencyError) as exc_info:
        validate_registry_consistency(_registry_with(om))
    ghost_source_errors = [e for e in exc_info.value.errors if "ghost-entity" in e and "source" in e]
    assert len(ghost_source_errors) == 1


def test_empty_permitted_relationships_passes() -> None:
    om = _StubOntology("test-ont", entity_names=["actor"], conn_names=["uses"])
    validate_registry_consistency(_registry_with(om))  # no rules → no errors
