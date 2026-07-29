"""Tests for AllowedBindingsSpec parsing and querying."""

from __future__ import annotations

import pytest

from src.domain.diagrams.allowed_bindings import (
    AllowedBindingsSpec,
    ConnectionBindingSpec,
    EntityBindingSpec,
    allowed_bindings_from_config,
    serialize_allowed_bindings,
)


class TestAllowedBindingsFromConfig:
    def test_empty_input_returns_empty_spec(self) -> None:
        spec = allowed_bindings_from_config(None)
        assert spec.is_empty()

    def test_non_mapping_returns_empty_spec(self) -> None:
        spec = allowed_bindings_from_config("not-a-dict")
        assert spec.is_empty()

    def test_empty_mapping_returns_empty_spec(self) -> None:
        spec = allowed_bindings_from_config({})
        assert spec.is_empty()

    def test_parses_entity_spec(self) -> None:
        raw = {
            "entity": {
                "container": {
                    "correspondence_kinds": ["represents", "refines", "traces-to"],
                    "default_correspondence_kind": "represents",
                    "target_forms": ["entity-id", "diagram-local"],
                }
            }
        }
        spec = allowed_bindings_from_config(raw)
        assert not spec.is_empty()
        assert "container" in spec.entity
        es = spec.entity["container"]
        assert isinstance(es, EntityBindingSpec)
        assert es.correspondence_kinds == ("represents", "refines", "traces-to")
        assert es.default_correspondence_kind == "represents"
        assert es.target_forms == ("entity-id", "diagram-local")
        assert es.visual_roles == ()

    def test_parses_entity_spec_with_visual_roles(self) -> None:
        raw = {
            "entity": {
                "container": {
                    "correspondence_kinds": ["represents"],
                    "default_correspondence_kind": "represents",
                    "target_forms": ["entity-id"],
                    "visual_roles": ["primary", "replica"],
                }
            }
        }
        spec = allowed_bindings_from_config(raw)
        assert spec.entity["container"].visual_roles == ("primary", "replica")

    def test_parses_connection_spec(self) -> None:
        raw = {
            "connection": {
                "c4-uses": {
                    "target_connection_types": ["serving", "flow"],
                    "target_connection_classes": ["dependency"],
                    "correspondence_kinds": ["abstracts", "represents", "traces-to"],
                    "default_correspondence_kind": "abstracts",
                    "target_forms": ["connection-id", "connection-ids"],
                }
            }
        }
        spec = allowed_bindings_from_config(raw)
        assert "c4-uses" in spec.connection
        cs = spec.connection["c4-uses"]
        assert isinstance(cs, ConnectionBindingSpec)
        assert cs.default_correspondence_kind == "abstracts"
        assert "serving" in cs.target_connection_types

    def test_raises_when_default_not_in_kinds_entity(self) -> None:
        raw = {
            "entity": {
                "container": {
                    "correspondence_kinds": ["represents"],
                    "default_correspondence_kind": "abstracts",  # not in list
                    "target_forms": ["entity-id"],
                }
            }
        }
        with pytest.raises(ValueError, match="default_correspondence_kind"):
            allowed_bindings_from_config(raw)

    def test_raises_when_default_not_in_kinds_connection(self) -> None:
        raw = {
            "connection": {
                "c4-uses": {
                    "correspondence_kinds": ["abstracts"],
                    "default_correspondence_kind": "represents",  # not in list
                    "target_forms": ["connection-id"],
                }
            }
        }
        with pytest.raises(ValueError, match="default_correspondence_kind"):
            allowed_bindings_from_config(raw)


class TestAllowedBindingsSpecQueries:
    def _make_spec(self) -> AllowedBindingsSpec:
        return allowed_bindings_from_config({
            "entity": {
                "container": {
                    "correspondence_kinds": ["represents", "traces-to"],
                    "default_correspondence_kind": "represents",
                    "target_forms": ["entity-id"],
                    "visual_roles": ["primary", "replica"],
                }
            },
            "connection": {
                "c4-uses": {
                    "correspondence_kinds": ["abstracts", "represents"],
                    "default_correspondence_kind": "abstracts",
                    "target_forms": ["connection-id", "connection-ids"],
                }
            },
        })

    def test_allowed_entity_kinds_returns_spec_kinds(self) -> None:
        spec = self._make_spec()
        kinds = spec.allowed_entity_kinds("container")
        assert kinds == frozenset({"represents", "traces-to"})

    def test_allowed_entity_kinds_returns_none_for_unknown_type(self) -> None:
        spec = self._make_spec()
        assert spec.allowed_entity_kinds("unknown-type") is None

    def test_allowed_connection_kinds_returns_spec_kinds(self) -> None:
        spec = self._make_spec()
        kinds = spec.allowed_connection_kinds("c4-uses")
        assert kinds == frozenset({"abstracts", "represents"})

    def test_allowed_connection_kinds_returns_none_for_unknown(self) -> None:
        spec = self._make_spec()
        assert spec.allowed_connection_kinds("unknown") is None

    def test_visual_roles_for_declared_type(self) -> None:
        spec = self._make_spec()
        assert spec.visual_roles_for("container") == ("primary", "replica")

    def test_visual_roles_for_undeclared_type_returns_empty(self) -> None:
        spec = self._make_spec()
        assert spec.visual_roles_for("unknown") == ()

    def test_empty_spec_is_empty(self) -> None:
        assert AllowedBindingsSpec.empty().is_empty()

    def test_non_empty_spec_is_not_empty(self) -> None:
        assert not self._make_spec().is_empty()


class TestSerializeAllowedBindings:
    def test_serialize_entity_spec(self) -> None:
        spec = allowed_bindings_from_config({
            "entity": {
                "container": {
                    "correspondence_kinds": ["represents", "traces-to"],
                    "default_correspondence_kind": "represents",
                    "target_forms": ["entity-id"],
                    "visual_roles": ["primary"],
                }
            }
        })
        out = serialize_allowed_bindings(spec)
        assert "entity" in out
        assert "container" in out["entity"]  # type: ignore[index]
        container_out = out["entity"]["container"]  # type: ignore[index]
        assert container_out["default_correspondence_kind"] == "represents"
        assert "primary" in container_out["visual_roles"]

    def test_serialize_connection_spec(self) -> None:
        spec = allowed_bindings_from_config({
            "connection": {
                "c4-uses": {
                    "target_connection_types": ["serving"],
                    "target_connection_classes": [],
                    "correspondence_kinds": ["abstracts"],
                    "default_correspondence_kind": "abstracts",
                    "target_forms": ["connection-id"],
                }
            }
        })
        out = serialize_allowed_bindings(spec)
        assert "connection" in out
        c = out["connection"]["c4-uses"]  # type: ignore[index]
        assert c["default_correspondence_kind"] == "abstracts"
        assert "serving" in c["target_connection_types"]

    def test_empty_visual_roles_not_in_output(self) -> None:
        spec = allowed_bindings_from_config({
            "entity": {
                "container": {
                    "correspondence_kinds": ["represents"],
                    "default_correspondence_kind": "represents",
                    "target_forms": ["entity-id"],
                }
            }
        })
        out = serialize_allowed_bindings(spec)
        container_out = out["entity"]["container"]  # type: ignore[index]
        assert "visual_roles" not in container_out
