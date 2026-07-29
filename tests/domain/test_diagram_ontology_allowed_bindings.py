"""Tests for allowed_bindings loading from diagram ontology.yaml files."""

from __future__ import annotations

from pathlib import Path

from src.domain.diagrams.diagram_ontology_loader import load_diagram_ontology

_C4_CONTAINER_DIR = Path("src/diagram_types/c4/container")
_C4_CONTEXT_DIR = Path("src/diagram_types/c4/system_context")
_C4_COMPONENT_DIR = Path("src/diagram_types/c4/component")
_ACTIVITY_DIR = Path("src/diagram_types/activity")


class TestC4ContainerAllowedBindings:
    def test_loads_allowed_bindings(self) -> None:
        ont = load_diagram_ontology(_C4_CONTAINER_DIR / "ontology.yaml")
        assert not ont.allowed_bindings.is_empty()

    def test_entity_container_default_is_represents(self) -> None:
        ont = load_diagram_ontology(_C4_CONTAINER_DIR / "ontology.yaml")
        spec = ont.allowed_bindings.entity.get("container")
        assert spec is not None
        assert spec.default_correspondence_kind == "represents"

    def test_entity_container_kinds_include_refines_and_traces(self) -> None:
        ont = load_diagram_ontology(_C4_CONTAINER_DIR / "ontology.yaml")
        spec = ont.allowed_bindings.entity["container"]
        assert "refines" in spec.correspondence_kinds
        assert "traces-to" in spec.correspondence_kinds

    def test_connection_c4_uses_default_is_abstracts(self) -> None:
        ont = load_diagram_ontology(_C4_CONTAINER_DIR / "ontology.yaml")
        spec = ont.allowed_bindings.connection.get("c4-uses")
        assert spec is not None
        assert spec.default_correspondence_kind == "abstracts"

    def test_connection_c4_uses_target_forms(self) -> None:
        ont = load_diagram_ontology(_C4_CONTAINER_DIR / "ontology.yaml")
        spec = ont.allowed_bindings.connection["c4-uses"]
        assert "connection-id" in spec.target_forms
        assert "connection-ids" in spec.target_forms

    def test_connection_c4_uses_target_connection_types(self) -> None:
        ont = load_diagram_ontology(_C4_CONTAINER_DIR / "ontology.yaml")
        spec = ont.allowed_bindings.connection["c4-uses"]
        assert "serving" in spec.target_connection_types
        assert "flow" in spec.target_connection_types


class TestC4SystemContextAllowedBindings:
    def test_has_person_and_software_system(self) -> None:
        ont = load_diagram_ontology(_C4_CONTEXT_DIR / "ontology.yaml")
        ab = ont.allowed_bindings
        assert "person" in ab.entity
        assert "software-system" in ab.entity

    def test_no_container_in_system_context(self) -> None:
        ont = load_diagram_ontology(_C4_CONTEXT_DIR / "ontology.yaml")
        assert "container" not in ont.allowed_bindings.entity


class TestC4ComponentAllowedBindings:
    def test_has_component_entity(self) -> None:
        ont = load_diagram_ontology(_C4_COMPONENT_DIR / "ontology.yaml")
        assert "component" in ont.allowed_bindings.entity
        spec = ont.allowed_bindings.entity["component"]
        assert spec.default_correspondence_kind == "represents"


class TestActivityAllowedBindings:
    def test_swimlane_spec_declared(self) -> None:
        ont = load_diagram_ontology(_ACTIVITY_DIR / "ontology.yaml")
        spec = ont.allowed_bindings.entity.get("swimlane")
        assert spec is not None
        assert spec.default_correspondence_kind == "represents"

    def test_action_spec_declared(self) -> None:
        ont = load_diagram_ontology(_ACTIVITY_DIR / "ontology.yaml")
        spec = ont.allowed_bindings.entity.get("action")
        assert spec is not None

    def test_fork_and_partition_have_no_spec(self) -> None:
        ont = load_diagram_ontology(_ACTIVITY_DIR / "ontology.yaml")
        assert "fork" not in ont.allowed_bindings.entity
        assert "partition" not in ont.allowed_bindings.entity


class TestOntologyWithoutAllowedBindings:
    def test_missing_allowed_bindings_key_returns_empty(self, tmp_path: Path) -> None:
        yaml_content = "entity_types:\n  box: {}\nconnection_types: {}\n"
        f = tmp_path / "ontology.yaml"
        f.write_text(yaml_content)
        ont = load_diagram_ontology(f)
        assert ont.allowed_bindings.is_empty()
