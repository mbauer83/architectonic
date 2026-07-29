"""Tests for bridge declaration parsing and startup validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from src.application.startup_validation import RegistryConsistencyError, validate_registry_consistency
from src.diagram_types._base import DiagramTypeBase
from src.domain.modules.bridges import BridgeDeclaration, bridges_from_config
from src.domain.modules.module_registry import ModuleRegistry
from src.domain.modules.module_types import ConnectionTypeName, ElementClassName, EntityTypeName
from src.domain.ontology_representation.ontology_protocol import DiagramOwnEntityTypeUiConfig, DiagramTypeUiConfig
from src.domain.ontology_representation.ontology_types import (
    ConnectionTypeInfo,
    EntityTypeInfo,
    MappingSourceSpec,
    PermittedMappingSpec,
)
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet

# ── Stub helpers ──────────────────────────────────────────────────────────────


def _entity_type(name: str, *, classes: tuple[str, ...] = ()) -> EntityTypeInfo:
    return EntityTypeInfo(
        artifact_type=name,
        prefix=name[:3].upper(),
        hierarchy=("test", name),
        classes=classes,
        create_when="",
        never_create_when="",
    )


def _conn_type(name: str) -> ConnectionTypeInfo:
    return ConnectionTypeInfo(artifact_type=name, conn_lang="test", classes=())


class _StubOntology:
    def __init__(
        self,
        name: str,
        entity_names: list[str],
        *,
        entity_classes: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._name = name
        ec = entity_classes or {}
        self._entity_types: dict[EntityTypeName, EntityTypeInfo] = {
            EntityTypeName(n): _entity_type(n, classes=ec.get(n, ())) for n in entity_names
        }
        self._connection_types: dict[ConnectionTypeName, ConnectionTypeInfo] = {}

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

    @property
    def element_classes(self) -> dict:
        return {}

    def entity_types_with_class(self, cls: ElementClassName) -> frozenset[EntityTypeName]:
        return frozenset(n for n, info in self._entity_types.items() if cls in info.classes)

    def connection_types_with_class(self, c: str) -> frozenset[ConnectionTypeName]:
        return frozenset()

    def permits_connection(self, src: Any, tgt: Any, conn: Any) -> bool:
        return False


def _diagram_entity_ui(
    etype: str,
    mapped_entity_types: tuple[str, ...] = (),
    mapped_entity_classes: tuple[str, ...] = (),
) -> DiagramOwnEntityTypeUiConfig:
    return DiagramOwnEntityTypeUiConfig(
        entity_type=etype,
        label=etype,
        plural=etype + "s",
        permitted_mappings=PermittedMappingSpec(
            entity_types=mapped_entity_types,
            entity_classes=mapped_entity_classes,
        ),
    )


class _StubDiagramType(DiagramTypeBase):
    def __init__(
        self,
        name: str,
        own_entity_type_names: list[str],
        *,
        bridge_decls: tuple[BridgeDeclaration, ...] = (),
        mapped_entity_types: dict[str, tuple[str, ...]] | None = None,
        mapped_entity_classes: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._name_str = name
        mets = mapped_entity_types or {}
        mecs = mapped_entity_classes or {}
        self._ui_config = DiagramTypeUiConfig(
            label=name,
            diagram_only_types=tuple(
                _diagram_entity_ui(
                    n,
                    mapped_entity_types=mets.get(n, ()),
                    mapped_entity_classes=mecs.get(n, ()),
                )
                for n in own_entity_type_names
            ),
        )
        self._bridges = bridge_decls
        self._config: dict[str, Any] = {}

    @property
    def name(self):  # type: ignore[override]
        return self._name_str

    @property
    def primary_ontology(self):  # type: ignore[override]
        from src.domain.modules.module_types import FreeOntology  # noqa: PLC0415
        return FreeOntology

    def accepts_entity_type(self, t: Any) -> bool:
        return False

    def accepts_connection_type(self, t: Any) -> bool:
        return False

    @property
    def own_entity_types(self):  # type: ignore[override]
        return {}

    @property
    def own_connection_types(self):  # type: ignore[override]
        return {}

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def bridges(self) -> tuple[BridgeDeclaration, ...]:
        return self._bridges

    def build_context_extras(self, repo: Any, diagram_id: str, diagram_entities: dict) -> dict:
        return {}

    def read_diagram_extras(self, parsed_source: dict) -> dict:
        return {}


def _make_bridge(
    *,
    name: str = "test-bridge",
    version: int = 1,
    from_module: str = "my-diagram",
    from_type: str = "container",
    to_module: str = "my-ontology",
    to_types: tuple[str, ...] = ("app-component",),
    preserves_classes: tuple[str, ...] = (),
    correspondence_kind: str = "represents",
) -> BridgeDeclaration:
    return BridgeDeclaration(
        name=name,
        version=version,
        from_module=from_module,
        from_type=from_type,
        to_module=to_module,
        to_types=to_types,
        preserves_classes=preserves_classes,
        correspondence_kind=correspondence_kind,
    )


def _make_registry(
    ontology: _StubOntology,
    diagram: _StubDiagramType,
) -> ModuleRegistry:
    reg = ModuleRegistry()
    reg.register_ontology(ontology)
    reg.register_diagram_type(diagram)
    return reg


# ── bridges_from_config ───────────────────────────────────────────────────────


class TestBridgesFromConfig:
    def test_none_returns_empty(self) -> None:
        assert bridges_from_config(None) == ()

    def test_non_list_returns_empty(self) -> None:
        assert bridges_from_config({"bridges": {}}) == ()

    def test_empty_list_returns_empty(self) -> None:
        assert bridges_from_config([]) == ()

    def test_parses_minimal_bridge(self) -> None:
        raw = [
            {
                "name": "my-bridge",
                "version": 1,
                "from": {"module": "c4-container", "type": "container"},
                "to": {"module": "archimate", "types": ["application-component"]},
                "preserves_classes": ["active-structure-element"],
                "correspondence_kind": "represents",
            }
        ]
        result = bridges_from_config(raw)
        assert len(result) == 1
        b = result[0]
        assert b.name == "my-bridge"
        assert b.from_module == "c4-container"
        assert b.from_type == "container"
        assert b.to_module == "archimate"
        assert b.to_types == ("application-component",)
        assert b.preserves_classes == ("active-structure-element",)
        assert b.correspondence_kind == "represents"

    def test_from_module_defaults_to_declaring_module(self) -> None:
        raw = [
            {
                "name": "b",
                "version": 1,
                "from": {"type": "container"},
                "to": {"module": "arch", "types": ["component"]},
                "correspondence_kind": "represents",
            }
        ]
        result = bridges_from_config(raw, declaring_module="c4")
        assert result[0].from_module == "c4"

    def test_skips_entries_without_name(self) -> None:
        raw = [{"version": 1, "from": {"type": "x"}, "to": {"module": "m", "types": ["y"]}}]
        assert bridges_from_config(raw) == ()

    def test_skips_non_mapping_entries(self) -> None:
        assert bridges_from_config(["not-a-dict", None]) == ()

    def test_multiple_bridges_parsed(self) -> None:
        raw = [
            {"name": "a", "from": {"type": "x"}, "to": {"module": "m", "types": ["y"]},
             "correspondence_kind": "represents"},
            {"name": "b", "from": {"type": "x"}, "to": {"module": "m", "types": ["z"]},
             "correspondence_kind": "abstracts"},
        ]
        result = bridges_from_config(raw)
        assert len(result) == 2
        assert result[0].name == "a"
        assert result[1].name == "b"


# ── bridge check validation ───────────────────────────────────────────────────


class TestBridgeValidation:
    def _ontology(self, entity_classes: dict[str, tuple[str, ...]] | None = None) -> _StubOntology:
        return _StubOntology(
            "my-ontology",
            ["app-component", "service"],
            entity_classes=entity_classes or {"app-component": ("structure-element",)},
        )

    def test_valid_bridge_no_errors(self) -> None:
        bridge = _make_bridge(
            from_module="my-diagram",
            from_type="container",
            to_module="my-ontology",
            to_types=("app-component",),
            preserves_classes=("structure-element",),
        )
        diagram = _StubDiagramType(
            "my-diagram",
            ["container"],
            bridge_decls=(bridge,),
            mapped_entity_types={"container": ("app-component",)},
        )
        reg = _make_registry(self._ontology(), diagram)
        validate_registry_consistency(reg)  # must not raise

    def test_unknown_from_type_raises(self) -> None:
        bridge = _make_bridge(from_type="unknown-type")
        diagram = _StubDiagramType("my-diagram", ["container"], bridge_decls=(bridge,))
        reg = _make_registry(self._ontology(), diagram)
        with pytest.raises(RegistryConsistencyError) as exc_info:
            validate_registry_consistency(reg)
        assert any("from.type" in e for e in exc_info.value.errors)

    def test_unknown_to_module_raises(self) -> None:
        bridge = _make_bridge(to_module="nonexistent-ontology")
        diagram = _StubDiagramType("my-diagram", ["container"], bridge_decls=(bridge,))
        reg = _make_registry(self._ontology(), diagram)
        with pytest.raises(RegistryConsistencyError) as exc_info:
            validate_registry_consistency(reg)
        assert any("to.module" in e for e in exc_info.value.errors)

    def test_unknown_to_type_raises(self) -> None:
        bridge = _make_bridge(to_types=("app-component", "nonexistent-type"))
        diagram = _StubDiagramType(
            "my-diagram", ["container"], bridge_decls=(bridge,),
            mapped_entity_types={"container": ("app-component", "nonexistent-type")},
        )
        reg = _make_registry(self._ontology(), diagram)
        with pytest.raises(RegistryConsistencyError) as exc_info:
            validate_registry_consistency(reg)
        assert any("nonexistent-type" in e for e in exc_info.value.errors)

    def test_invalid_correspondence_kind_raises(self) -> None:
        bridge = _make_bridge(correspondence_kind="not-a-core-kind")
        diagram = _StubDiagramType(
            "my-diagram", ["container"], bridge_decls=(bridge,),
            mapped_entity_types={"container": ("app-component",)},
        )
        reg = _make_registry(self._ontology(), diagram)
        with pytest.raises(RegistryConsistencyError) as exc_info:
            validate_registry_consistency(reg)
        assert any("correspondence_kind" in e for e in exc_info.value.errors)

    def test_class_preservation_failure_raises(self) -> None:
        # service lacks structure-element but bridge claims to preserve it
        ontology = _StubOntology(
            "my-ontology",
            ["app-component", "service"],
            entity_classes={
                "app-component": ("structure-element",),
                "service": ("behavior-element",),  # no structure-element
            },
        )
        bridge = _make_bridge(
            to_types=("app-component", "service"),
            preserves_classes=("structure-element",),
        )
        diagram = _StubDiagramType(
            "my-diagram", ["container"], bridge_decls=(bridge,),
            mapped_entity_types={"container": ("app-component", "service")},
        )
        reg = _make_registry(ontology, diagram)
        with pytest.raises(RegistryConsistencyError) as exc_info:
            validate_registry_consistency(reg)
        assert any("structure-element" in e and "service" in e for e in exc_info.value.errors)

    def test_class_preservation_all_types_have_class_passes(self) -> None:
        ontology = _StubOntology(
            "my-ontology",
            ["app-component", "service"],
            entity_classes={
                "app-component": ("active-structure-element",),
                "service": ("active-structure-element",),
            },
        )
        bridge = _make_bridge(
            to_types=("app-component", "service"),
            preserves_classes=("active-structure-element",),
        )
        diagram = _StubDiagramType(
            "my-diagram", ["container"], bridge_decls=(bridge,),
            mapped_entity_types={"container": ("app-component", "service")},
        )
        reg = _make_registry(ontology, diagram)
        validate_registry_consistency(reg)  # must not raise

    def test_descent_overlap_to_type_not_in_permitted_mappings_raises(self) -> None:
        bridge = _make_bridge(
            to_types=("app-component", "service"),
            # permitted_mappings for container only includes app-component
        )
        diagram = _StubDiagramType(
            "my-diagram", ["container"], bridge_decls=(bridge,),
            mapped_entity_types={"container": ("app-component",)},  # service not allowed
        )
        reg = _make_registry(self._ontology(), diagram)
        with pytest.raises(RegistryConsistencyError) as exc_info:
            validate_registry_consistency(reg)
        assert any("permitted_mappings" in e or "contradicts" in e for e in exc_info.value.errors)

    def test_descent_overlap_uses_class_based_permitted_mapping_scope(self) -> None:
        bridge = _make_bridge(to_types=("app-component",))
        diagram = _StubDiagramType(
            "my-diagram",
            ["container"],
            bridge_decls=(bridge,),
            mapped_entity_classes={"container": ("structure-element",)},
        )
        reg = _make_registry(self._ontology(), diagram)

        validate_registry_consistency(reg)  # must not raise

    def test_no_bridges_no_errors(self) -> None:
        diagram = _StubDiagramType("my-diagram", ["container"], bridge_decls=())
        reg = _make_registry(self._ontology(), diagram)
        validate_registry_consistency(reg)  # must not raise


# ── permitted_mappings source-ontology validation ─────────────────────────────


class TestPermittedMappingSourceValidation:
    def _diagram_with_source(self, ontology_token: str) -> _StubDiagramType:
        diagram = _StubDiagramType("my-diagram", [])
        diagram._ui_config = DiagramTypeUiConfig(
            label="my-diagram",
            diagram_only_types=(
                DiagramOwnEntityTypeUiConfig(
                    entity_type="lane",
                    label="lane",
                    plural="lanes",
                    permitted_mappings=PermittedMappingSpec(
                        sources=(MappingSourceSpec(ontology=ontology_token, entity_type="role"),)
                    ),
                ),
            ),
        )
        return diagram

    def test_known_ontology_token_passes(self) -> None:
        diagram = self._diagram_with_source("my-ontology")
        reg = _make_registry(_StubOntology("my-ontology", ["role"]), diagram)
        validate_registry_consistency(reg)  # must not raise

    def test_unknown_ontology_token_raises(self) -> None:
        diagram = self._diagram_with_source("nonexistent-ontology")
        reg = _make_registry(_StubOntology("my-ontology", ["role"]), diagram)
        with pytest.raises(RegistryConsistencyError) as exc_info:
            validate_registry_consistency(reg)
        assert any(
            "permitted_mappings source ontology" in e and "nonexistent-ontology" in e
            for e in exc_info.value.errors
        )


# ── real registry integration ─────────────────────────────────────────────────


class TestRealRegistryBridges:
    def test_real_registry_bridge_check_passes(self) -> None:
        """C4 container module bridge declarations pass the minimum bridge check."""
        from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

        reg = build_module_registry()
        dt = reg.find_diagram_type("c4-container")
        assert dt is not None
        assert len(dt.bridges) == 3  # three bridges for container type
        # validate_registry_consistency is called inside build_module_registry
        # so reaching here means the bridges passed the check

    def test_c4_container_bridge_names(self) -> None:
        from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

        reg = build_module_registry()
        dt = reg.find_diagram_type("c4-container")
        assert dt is not None
        names = {b.name for b in dt.bridges}
        assert names == {
            "c4-container-to-archimate-active",
            "c4-container-to-archimate-service",
            "c4-container-to-archimate-data",
        }

    def test_c4_container_bridges_have_valid_correspondence_kinds(self) -> None:
        from src.domain.diagrams.bindings import CORE_CORRESPONDENCE_KINDS  # noqa: PLC0415
        from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

        reg = build_module_registry()
        dt = reg.find_diagram_type("c4-container")
        assert dt is not None
        for b in dt.bridges:
            assert b.correspondence_kind in CORE_CORRESPONDENCE_KINDS
