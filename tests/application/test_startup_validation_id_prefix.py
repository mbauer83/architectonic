"""WU-0.1 acceptance: startup validation enforces id_prefix rules for workspace-scoped types."""

from __future__ import annotations

import pytest

from src.application.startup_validation import RegistryConsistencyError, validate_registry_consistency
from src.domain.diagrams.diagram_type_config import DiagramOwnEntityTypeUiConfig, DiagramTypeUiConfig
from src.domain.modules.module_types import DiagramTypeName, EntityTypeName
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.relationships.permitted_relationships import PermittedRelationshipSet


class _StubDiagramType:
    def __init__(self, name: str, own_entity_types: list[tuple]) -> None:
        self._name = DiagramTypeName(name)
        ui_entries = []
        self._own_entity_types = {}
        for etype, scope, prefix in own_entity_types:
            ui_entries.append(
                DiagramOwnEntityTypeUiConfig(
                    entity_type=etype,
                    label=etype.title(),
                    plural=etype.title() + "s",
                    identity_scope=scope,
                    id_prefix=prefix,
                )
            )
            self._own_entity_types[EntityTypeName(etype)] = EntityTypeInfo(
                artifact_type=etype,
                prefix="",
                hierarchy=(),
                classes=(),
                create_when="",
                never_create_when="",
                identity_scope=scope,
                id_prefix=prefix,
            )
        self._ui_config = DiagramTypeUiConfig(
            label=name,
            diagram_only_types=tuple(ui_entries),
        )

    @property
    def name(self) -> DiagramTypeName:
        return self._name

    @property
    def ui_config(self) -> DiagramTypeUiConfig:
        return self._ui_config

    @property
    def own_entity_types(self) -> dict:
        return self._own_entity_types

    @property
    def own_permitted_relationships(self) -> PermittedRelationshipSet:
        return PermittedRelationshipSet.empty()

    @property
    def bridges(self):
        return ()

    @property
    def element_classes(self):
        return {}


class _StubRegistry:
    def __init__(self, diagram_types: list[_StubDiagramType]) -> None:
        self._dt = {str(dt.name): dt for dt in diagram_types}

    def all_ontologies(self):
        return {}

    def all_diagram_types(self):
        return self._dt

    def all_entity_types(self):
        return {}

    def all_connection_types(self):
        return {}

    def all_element_classes(self):
        return {}


def _validate(diagram_types):
    reg = _StubRegistry(diagram_types)
    validate_registry_consistency(reg)


def test_valid_workspace_type_passes():
    _validate([_StubDiagramType("dt1", [("classifier", "workspace", "CLF")])])


def test_workspace_type_missing_prefix_fails():
    with pytest.raises(RegistryConsistencyError) as exc_info:
        _validate([_StubDiagramType("dt1", [("classifier", "workspace", None)])])
    assert "id_prefix" in str(exc_info.value)
    assert "classifier" in str(exc_info.value)


def test_workspace_type_lowercase_prefix_fails():
    with pytest.raises(RegistryConsistencyError) as exc_info:
        _validate([_StubDiagramType("dt1", [("classifier", "workspace", "clf")])])
    assert "does not match grammar" in str(exc_info.value)


def test_workspace_type_mixed_case_prefix_fails():
    with pytest.raises(RegistryConsistencyError) as exc_info:
        _validate([_StubDiagramType("dt1", [("classifier", "workspace", "Clf")])])
    assert "does not match grammar" in str(exc_info.value)


def test_duplicate_prefix_across_types_fails():
    with pytest.raises(RegistryConsistencyError) as exc_info:
        _validate([
            _StubDiagramType("dt1", [("classifier", "workspace", "CLF"), ("node", "workspace", "CLF")]),
        ])
    assert "already declared" in str(exc_info.value)


def test_duplicate_prefix_across_diagram_types_fails():
    with pytest.raises(RegistryConsistencyError) as exc_info:
        _validate([
            _StubDiagramType("dt1", [("classifier", "workspace", "CLF")]),
            _StubDiagramType("dt2", [("node", "workspace", "CLF")]),
        ])
    assert "already declared" in str(exc_info.value)


def test_diagram_scoped_type_no_prefix_required():
    _validate([_StubDiagramType("dt1", [("node", "diagram", None)])])


def test_real_registry_passes():
    import src.infrastructure.app_bootstrap as app_bootstrap
    reg = app_bootstrap.build_module_registry(complete_vocabulary=True)
    validate_registry_consistency(reg)
