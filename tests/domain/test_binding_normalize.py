"""Tests for binding shorthand normalization (§1.2)."""

from __future__ import annotations

import pytest

from src.application.modeling.binding_normalize import normalize_bindings


class TestNormalizeBindings:
    def test_empty_inputs(self) -> None:
        assert normalize_bindings(None, None) == []

    def test_explicit_bindings_only(self) -> None:
        explicit = [
            {
                "id": "bind-1",
                "subject": {"kind": "entity", "id": "box-web"},
                "correspondence_kind": "represents",
                "target": {"entity_id": "APP@1.a.Web"},
            }
        ]
        result = normalize_bindings(None, explicit)
        assert len(result) == 1
        assert result[0].id == "bind-1"
        assert result[0].target.entity_id == "APP@1.a.Web"

    def test_shorthand_on_entity_produces_binding(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {
                    "id": "box-api",
                    "label": "API",
                    "binding": {"correspondence_kind": "represents", "target": {"entity_id": "APP@1.a.Api"}},
                }
            ]
        }
        result = normalize_bindings(entities, None)
        assert len(result) == 1
        b = result[0]
        assert b.id == "bind-box-api"
        assert b.subject.kind == "entity"
        assert b.subject.id == "box-api"
        assert b.correspondence_kind == "represents"
        assert b.target.entity_id == "APP@1.a.Api"

    def test_default_correspondence_kind_is_represents(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {"id": "box-db", "label": "DB", "binding": {"target": {"entity_id": "APP@1.a.Db"}}}
            ]
        }
        result = normalize_bindings(entities, None)
        assert result[0].correspondence_kind == "represents"

    def test_shorthand_and_explicit_merged(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {
                    "id": "box-api",
                    "label": "API",
                    "binding": {"target": {"entity_id": "APP@1.a.Api"}},
                }
            ]
        }
        explicit = [
            {
                "id": "bind-scope",
                "subject": {"kind": "diagram"},
                "correspondence_kind": "scoped-by",
                "target": {"entity_id": "SYS@1.s.Sys"},
            }
        ]
        result = normalize_bindings(entities, explicit)
        assert len(result) == 2
        ids = {b.id for b in result}
        assert "bind-scope" in ids
        assert "bind-box-api" in ids

    def test_explicit_wins_over_shorthand_with_same_id(self) -> None:
        """If explicit binding has id=bind-{element_id}, shorthand is silently dropped."""
        entities: dict[str, object] = {
            "container": [
                {
                    "id": "box-api",
                    "label": "API",
                    "binding": {"target": {"entity_id": "APP@1.a.Api"}},
                }
            ]
        }
        explicit = [
            {
                "id": "bind-box-api",
                "subject": {"kind": "entity", "id": "box-api"},
                "correspondence_kind": "traces-to",
                "target": {"entity_id": "APP@1.x.Other"},
            }
        ]
        result = normalize_bindings(entities, explicit)
        assert len(result) == 1
        assert result[0].correspondence_kind == "traces-to"

    def test_items_without_binding_are_skipped(self) -> None:
        entities: dict[str, object] = {
            "container": [{"id": "box-unbound", "label": "Unbound"}]
        }
        result = normalize_bindings(entities, None)
        assert result == []

    def test_backing_entity_id_produces_occurrence_binding(self) -> None:
        entities: dict[str, object] = {
            "occurrence": [
                {
                    "id": "repo-left",
                    "backing_entity_id": "BOB@1.a.enterprise-repository",
                    "visual_role": "left-context",
                }
            ]
        }
        result = normalize_bindings(entities, None)
        assert len(result) == 1
        assert result[0].id == "bind-repo-left"
        assert result[0].subject.id == "repo-left"
        assert result[0].target.entity_id == "BOB@1.a.enterprise-repository"
        assert result[0].visual_role == "left-context"

    def test_multiple_entity_types(self) -> None:
        entities: dict[str, object] = {
            "person": [{"id": "usr-1", "label": "User", "binding": {"target": {"entity_id": "ACT@1.a.User"}}}],
            "container": [{"id": "svc-1", "label": "API", "binding": {"target": {"entity_id": "APP@1.a.Api"}}}],
        }
        result = normalize_bindings(entities, None)
        assert len(result) == 2

    def test_scoped_by_shorthand_allowed(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {"id": "box-1", "label": "X",
                 "binding": {"correspondence_kind": "scoped-by", "target": {"entity_id": "SYS@1.s.S"}}}
            ]
        }
        result = normalize_bindings(entities, None)
        assert result[0].correspondence_kind == "scoped-by"

    def test_refines_shorthand_allowed(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {"id": "box-1", "label": "X",
                 "binding": {"correspondence_kind": "refines", "target": {"entity_id": "APP@1.a.A"}}}
            ]
        }
        result = normalize_bindings(entities, None)
        assert result[0].correspondence_kind == "refines"

    def test_traces_to_shorthand_allowed(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {"id": "box-1", "label": "X",
                 "binding": {"correspondence_kind": "traces-to", "target": {"entity_id": "APP@1.a.A"}}}
            ]
        }
        result = normalize_bindings(entities, None)
        assert result[0].correspondence_kind == "traces-to"


class TestNormalizeBindingsRejections:
    def test_abstracts_shorthand_rejected(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {"id": "box-1", "label": "X",
                 "binding": {"correspondence_kind": "abstracts", "target": {"entity_id": "APP@1.a.A"}}}
            ]
        }
        with pytest.raises(ValueError, match="cannot be expressed as shorthand"):
            normalize_bindings(entities, None)

    def test_connection_ids_in_shorthand_rejected(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {
                    "id": "box-1",
                    "label": "X",
                    "binding": {
                        "target": {"connection_ids": ["A@1---B@2@@serving"]}
                    },
                }
            ]
        }
        with pytest.raises(ValueError, match="connection_ids is a multi-target"):
            normalize_bindings(entities, None)

    def test_connection_path_in_shorthand_rejected(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {
                    "id": "box-1",
                    "label": "X",
                    "binding": {
                        "target": {"connection_path": [{"id": "A---B@@serving"}]}
                    },
                }
            ]
        }
        with pytest.raises(ValueError, match="connection_path cannot be expressed"):
            normalize_bindings(entities, None)

    def test_entity_without_id_raises(self) -> None:
        entities: dict[str, object] = {
            "container": [{"label": "No ID", "binding": {"target": {"entity_id": "APP@1.a.A"}}}]
        }
        with pytest.raises(ValueError, match="no 'id'"):
            normalize_bindings(entities, None)

    def test_unknown_correspondence_kind_rejected(self) -> None:
        entities: dict[str, object] = {
            "container": [
                {
                    "id": "box-1",
                    "label": "X",
                    "binding": {"correspondence_kind": "allocated-to", "target": {"entity_id": "APP@1.a.A"}},
                }
            ]
        }
        with pytest.raises(ValueError, match="not a core correspondence kind"):
            normalize_bindings(entities, None)

    def test_binding_not_dict_raises(self) -> None:
        entities: dict[str, object] = {
            "container": [{"id": "box-1", "label": "X", "binding": "bad"}]
        }
        with pytest.raises(ValueError, match="must be a dict"):
            normalize_bindings(entities, None)
