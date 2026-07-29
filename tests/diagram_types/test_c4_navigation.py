"""Tests for c4/_navigation.py — C4 diagram navigation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from src.diagram_types.c4._navigation import (
    build_c4_navigation,
    item_entity_ids,
    scope_entity_id,
)

# ── helpers ───────────────────────────────────────────────────────────────────


@dataclass
class FakeDiagramRecord:
    artifact_id: str
    diagram_type: str
    name: str
    extra: dict[str, Any]


def _make_repo(diagrams: list[FakeDiagramRecord]) -> MagicMock:
    repo = MagicMock()
    repo.list_diagrams = lambda: diagrams
    repo.get_entity = lambda eid: None
    return repo


# ── scope_entity_id ────────────────────────────────────────────────────────────


class TestScopeEntityId:
    def test_explicit_field_returned(self) -> None:
        de: dict[str, Any] = {"_scope_entity_id": "ENT@1.A.a"}
        assert scope_entity_id(de) == "ENT@1.A.a"

    def test_scope_from_item(self) -> None:
        de = {"items": [{"entity_id": "ENT@2.B.b", "scope": True}]}
        assert scope_entity_id(de) == "ENT@2.B.b"

    def test_item_without_scope_skipped(self) -> None:
        de = {"items": [{"entity_id": "ENT@2.B.b"}]}
        assert scope_entity_id(de) == ""

    def test_underscore_key_skipped(self) -> None:
        de = {"_meta": [{"entity_id": "ENT@3.C.c", "scope": True}]}
        assert scope_entity_id(de) == ""

    def test_non_list_value_skipped(self) -> None:
        de = {"items": "not-a-list"}
        assert scope_entity_id(de) == ""

    def test_empty_dict_returns_empty(self) -> None:
        assert scope_entity_id({}) == ""


# ── item_entity_ids ───────────────────────────────────────────────────────────


class TestItemEntityIds:
    def test_returns_entity_ids_from_items(self) -> None:
        de = {"containers": [{"entity_id": "ENT@1.A.a"}, {"entity_id": "ENT@2.B.b"}]}
        result = item_entity_ids(de)
        assert result == {"ENT@1.A.a", "ENT@2.B.b"}

    def test_underscore_keys_skipped(self) -> None:
        de = {"_private": [{"entity_id": "ENT@3.C.c"}], "normal": [{"entity_id": "ENT@4.D.d"}]}
        result = item_entity_ids(de)
        assert "ENT@3.C.c" not in result
        assert "ENT@4.D.d" in result

    def test_non_list_skipped(self) -> None:
        de = {"items": "not-a-list", "valid": [{"entity_id": "ENT@5.E.e"}]}
        result = item_entity_ids(de)
        assert result == {"ENT@5.E.e"}

    def test_empty_dict_returns_empty_set(self) -> None:
        assert item_entity_ids({}) == set()


# ── build_c4_navigation ───────────────────────────────────────────────────────


class TestBuildC4Navigation:
    def test_unknown_diagram_type_returns_none(self) -> None:
        repo = _make_repo([])
        result = build_c4_navigation(repo, "DIAG@1", "not-a-c4-type", {})
        assert result is None

    def test_no_related_diagrams_returns_empty_lists(self) -> None:
        repo = _make_repo([])
        result = build_c4_navigation(repo, "DIAG@1", "c4-system-context", {"_scope_entity_id": "ENT@1.A.a"})
        assert result is not None
        assert result["parent_diagrams"] == []
        assert result["child_diagrams"] == []
        assert result["current_level"] == 1

    def test_same_scope_context_and_container_linked(self) -> None:
        other = FakeDiagramRecord(
            artifact_id="DIAG@2.B.b",
            diagram_type="c4-container",
            name="Container Diag",
            extra={"diagram-entities": {"_scope_entity_id": "ENT@1.A.a"}},
        )
        repo = _make_repo([other])
        result = build_c4_navigation(repo, "DIAG@1.A.a", "c4-system-context", {"_scope_entity_id": "ENT@1.A.a"})
        assert result is not None
        child_ids = [d["diagram_id"] for d in result["child_diagrams"]]
        assert "DIAG@2.B.b" in child_ids

    def test_container_child_links_component_diagrams(self) -> None:
        component_diag = FakeDiagramRecord(
            artifact_id="DIAG@3.C.c",
            diagram_type="c4-component",
            name="Component Diag",
            extra={"diagram-entities": {"_scope_entity_id": "ENT@2.B.b"}},
        )
        repo = _make_repo([component_diag])
        current_de: dict[str, Any] = {
            "containers": [{"entity_id": "ENT@2.B.b"}],
            "_scope_entity_id": "ENT@1.A.a",
        }
        result = build_c4_navigation(repo, "DIAG@2.A.a", "c4-container", current_de)
        assert result is not None
        child_ids = [d["diagram_id"] for d in result["child_diagrams"]]
        assert "DIAG@3.C.c" in child_ids

    def test_component_links_parent_container(self) -> None:
        container_diag = FakeDiagramRecord(
            artifact_id="DIAG@2.B.b",
            diagram_type="c4-container",
            name="Container",
            extra={"diagram-entities": {"containers": [{"entity_id": "ENT@2.B.b"}]}},
        )
        repo = _make_repo([container_diag])
        current_de: dict[str, Any] = {"_scope_entity_id": "ENT@2.B.b"}
        result = build_c4_navigation(repo, "DIAG@3.C.c", "c4-component", current_de)
        assert result is not None
        parent_ids = [d["diagram_id"] for d in result["parent_diagrams"]]
        assert "DIAG@2.B.b" in parent_ids

    def test_skips_current_diagram_in_loop(self) -> None:
        self_diag = FakeDiagramRecord(
            artifact_id="DIAG@1.A.a",
            diagram_type="c4-system-context",
            name="Self",
            extra={"diagram-entities": {"_scope_entity_id": "ENT@1.A.a"}},
        )
        repo = _make_repo([self_diag])
        result = build_c4_navigation(repo, "DIAG@1.A.a", "c4-system-context", {"_scope_entity_id": "ENT@1.A.a"})
        assert result is not None
        assert result["parent_diagrams"] == []
        assert result["child_diagrams"] == []

    def test_scope_entity_name_resolved(self) -> None:
        entity_mock = MagicMock()
        entity_mock.name = "My System"
        repo = _make_repo([])
        repo.get_entity = lambda eid: entity_mock if eid == "ENT@1.A.a" else None
        result = build_c4_navigation(repo, "DIAG@1", "c4-system-context", {"_scope_entity_id": "ENT@1.A.a"})
        assert result is not None
        assert result["scope_entity_name"] == "My System"


# ── model-backed diagrams (scope in a scoped-by binding, items in entity-ids-used) ───────────


def _scoped_by(entity_id: str) -> list[dict[str, Any]]:
    return [{
        "id": "bind-scope",
        "subject": {"kind": "diagram"},
        "correspondence_kind": "scoped-by",
        "target": {"entity_id": entity_id},
    }]


class TestModelBackedNavigation:
    """Regression: model-backed C4 diagrams keep diagram-entities empty and record scope in a
    scoped-by binding + items in entity-ids-used. Navigation must resolve both, so drill-down
    links populate (previously empty → the GUI nav block stayed hidden)."""

    def test_scope_from_binding_and_items_from_entity_ids_used(self) -> None:
        context = FakeDiagramRecord(
            "DIAG@CTX", "c4-system-context", "AMP — System Context",
            {"diagram-entities": {}, "bindings": _scoped_by("ENT@AMP"), "entity-ids-used": ["ENT@AMP"]},
        )
        container = FakeDiagramRecord(
            "DIAG@CONT", "c4-container", "AMP — Containers",
            {"diagram-entities": {}, "bindings": _scoped_by("ENT@AMP"),
             "entity-ids-used": ["ENT@AMP", "ENT@BACKEND"]},
        )
        backend_components = FakeDiagramRecord(
            "DIAG@COMP", "c4-component", "Architecture Backend — Components",
            {"diagram-entities": {}, "bindings": _scoped_by("ENT@BACKEND"), "entity-ids-used": ["ENT@BACKEND"]},
        )
        repo = _make_repo([context, container, backend_components])
        # Called exactly as the backend does for a model-backed diagram: empty diagram_entities.
        result = build_c4_navigation(repo, "DIAG@CONT", "c4-container", {})
        assert result is not None
        assert result["scope_entity_id"] == "ENT@AMP"
        assert "DIAG@CTX" in [d["diagram_id"] for d in result["parent_diagrams"]]
        assert "DIAG@COMP" in [d["diagram_id"] for d in result["child_diagrams"]]

    def test_component_finds_parent_container_via_binding_scope(self) -> None:
        container = FakeDiagramRecord(
            "DIAG@CONT", "c4-container", "AMP — Containers",
            {"diagram-entities": {}, "bindings": _scoped_by("ENT@AMP"),
             "entity-ids-used": ["ENT@AMP", "ENT@BACKEND"]},
        )
        component = FakeDiagramRecord(
            "DIAG@COMP", "c4-component", "Architecture Backend — Components",
            {"diagram-entities": {}, "bindings": _scoped_by("ENT@BACKEND"), "entity-ids-used": ["ENT@BACKEND"]},
        )
        repo = _make_repo([container, component])
        result = build_c4_navigation(repo, "DIAG@COMP", "c4-component", {})
        assert result is not None
        assert result["scope_entity_id"] == "ENT@BACKEND"
        assert "DIAG@CONT" in [d["diagram_id"] for d in result["parent_diagrams"]]
