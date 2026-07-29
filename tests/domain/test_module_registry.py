"""Unit tests for ModuleRegistry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from src.domain.modules.module_registry import ModuleRegistry
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo, EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

# ── Minimal stub implementations ─────────────────────────────────────────────


def _entity_type(name: str, domain: str = "test", classes: tuple[str, ...] = ()) -> EntityTypeInfo:
    return EntityTypeInfo(
        artifact_type=name,
        prefix=name[:3].upper(),
        hierarchy=(domain, name),
        classes=classes,
        create_when="",
        never_create_when="",
    )


def _conn_type(name: str, classes: tuple[str, ...] = ()) -> ConnectionTypeInfo:
    return ConnectionTypeInfo(
        artifact_type=name,
        conn_lang="test",
        classes=classes,
    )


class _StubOntology:
    def __init__(self, name: str, entity_names: list[str], conn_names: list[str]) -> None:
        self._name = name
        self._entity_types: dict[EntityTypeName, EntityTypeInfo] = {
            EntityTypeName(n): _entity_type(n) for n in entity_names
        }
        self._connection_types: dict[ConnectionTypeName, ConnectionTypeInfo] = {
            ConnectionTypeName(n): _conn_type(n) for n in conn_names
        }

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
        return PermittedRelationshipSet.empty()

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        return frozenset(n for n, info in self._entity_types.items() if cls in info.classes)

    def connection_types_with_class(self, cls: str) -> frozenset[ConnectionTypeName]:
        return frozenset(n for n, info in self._connection_types.items() if cls in info.classes)

    def permits_connection(self, src: Any, tgt: Any, conn: Any) -> bool:
        return False


class _StubDiagramType:
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    # Protocol methods — minimal stubs
    def accepts_entity_type(self, t: Any) -> bool:
        return True

    def accepts_connection_type(self, t: Any) -> bool:
        return True

    def effective_entity_types(self) -> dict:
        return {}

    def effective_connection_types(self) -> dict:
        return {}

    @property
    def own_entity_types(self) -> dict:
        return {}

    @property
    def own_connection_types(self) -> dict:
        return {}

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def effective_permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def primary_ontology(self) -> Any:
        return None

    @property
    def renderer(self) -> Any:
        return None


# ── Registration tests ────────────────────────────────────────────────────────


class TestRegistration:
    def test_register_and_get_ontology(self) -> None:
        reg = ModuleRegistry()
        onto = _StubOntology("onto-a", ["entity-x"], [])
        reg.register_ontology(onto)
        assert reg.get_ontology("onto-a") is onto

    def test_register_duplicate_raises(self) -> None:
        reg = ModuleRegistry()
        onto = _StubOntology("onto-a", [], [])
        reg.register_ontology(onto)
        with pytest.raises(ValueError, match="already registered"):
            reg.register_ontology(_StubOntology("onto-a", [], []))

    def test_replace_ontology_succeeds(self) -> None:
        reg = ModuleRegistry()
        o1 = _StubOntology("onto-a", ["e1"], [])
        o2 = _StubOntology("onto-a", ["e2"], [])
        reg.register_ontology(o1)
        reg.replace_ontology(o2)
        assert reg.get_ontology("onto-a") is o2

    def test_unregister_ontology(self) -> None:
        reg = ModuleRegistry()
        reg.register_ontology(_StubOntology("onto-a", [], []))
        reg.unregister_ontology("onto-a")
        assert reg.find_ontology("onto-a") is None

    def test_unregister_missing_raises(self) -> None:
        reg = ModuleRegistry()
        with pytest.raises(KeyError):
            reg.unregister_ontology("no-such")

    def test_register_and_get_diagram_type(self) -> None:
        reg = ModuleRegistry()
        dk = _StubDiagramType("dk-a")
        reg.register_diagram_type(dk)
        assert reg.get_diagram_type("dk-a") is dk

    def test_register_duplicate_diagram_kind_raises(self) -> None:
        reg = ModuleRegistry()
        reg.register_diagram_type(_StubDiagramType("dk-a"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register_diagram_type(_StubDiagramType("dk-a"))


# ── Query tests ───────────────────────────────────────────────────────────────


class TestQueries:
    def test_get_unknown_ontology_raises(self) -> None:
        reg = ModuleRegistry()
        with pytest.raises(KeyError, match="No ontology"):
            reg.get_ontology("missing")

    def test_find_unknown_returns_none(self) -> None:
        reg = ModuleRegistry()
        assert reg.find_ontology("x") is None
        assert reg.find_diagram_type("x") is None

    def test_all_entity_types_merges_across_ontologies(self) -> None:
        reg = ModuleRegistry()
        reg.register_ontology(_StubOntology("o1", ["e-a", "e-b"], []))
        reg.register_ontology(_StubOntology("o2", ["e-c"], []))
        all_types = reg.all_entity_types()
        assert set(all_types) == {EntityTypeName("e-a"), EntityTypeName("e-b"), EntityTypeName("e-c")}

    def test_entity_types_with_class_aggregates(self) -> None:
        reg = ModuleRegistry()

        et1 = EntityTypeInfo("et-1", "ET1", ("d", "et-1"), ("my-class",), "", "")
        et2 = EntityTypeInfo("et-2", "ET2", ("d", "et-2"), (), "", "")

        class _O(_StubOntology):
            @property
            def entity_types(self):
                return {EntityTypeName("et-1"): et1, EntityTypeName("et-2"): et2}

            def entity_types_with_class(self, cls):
                return frozenset(n for n, info in self.entity_types.items() if cls in info.classes)

        reg.register_ontology(_O("o", [], []))
        result = reg.entity_types_with_class(ElementClassName("my-class"))
        assert result == frozenset({EntityTypeName("et-1")})
        assert EntityTypeName("et-2") not in result

    def test_connection_types_with_class(self) -> None:
        reg = ModuleRegistry()

        ct1 = ConnectionTypeInfo("ct-1", "test", classes=("flow",))
        ct2 = ConnectionTypeInfo("ct-2", "test", classes=())

        class _O(_StubOntology):
            @property
            def connection_types(self):
                return {ConnectionTypeName("ct-1"): ct1, ConnectionTypeName("ct-2"): ct2}

            def connection_types_with_class(self, clf):
                return frozenset(n for n, info in self.connection_types.items() if clf in info.classes)

        reg.register_ontology(_O("o", [], []))
        assert reg.connection_types_with_class("flow") == frozenset({ConnectionTypeName("ct-1")})
        assert reg.connection_types_with_class("structural") == frozenset()

    def test_domain_order_excludes_internal(self) -> None:
        reg = ModuleRegistry()

        et_a = EntityTypeInfo("e-a", "EA", ("motivation", "e-a"), (), "", "")
        et_b = EntityTypeInfo("e-b", "EB", ("strategy", "e-b"), (), "", "", internal=False)
        et_c = EntityTypeInfo("e-c", "EC", ("common", "e-c"), (), "", "", internal=True)

        class _O(_StubOntology):
            @property
            def entity_types(self):
                return {
                    EntityTypeName("e-a"): et_a,
                    EntityTypeName("e-b"): et_b,
                    EntityTypeName("e-c"): et_c,
                }

        reg.register_ontology(_O("o", [], []))
        order = reg.domain_order()
        assert "motivation" in order
        assert "strategy" in order
        assert "common" not in order  # internal=True
