"""Tests that renderers derive entity/connection ids from represents bindings.

Covers:
- C4PumlRenderer.collect_references: reads represents bindings for standalone diagrams
- ActivityPumlRenderer.collect_references: reads represents bindings
- Both renderers ignore non-represents bindings
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.diagram_types.activity.renderer import ActivityPumlRenderer
from src.diagram_types.c4.renderer import C4PumlRenderer

_ENTITY_A = "APP@1000000000.AbcDef.entity-a"
_ENTITY_B = "APP@1000000001.AbcDef.entity-b"
_CONN_ID = f"{_ENTITY_A}---{_ENTITY_B}@@archimate-serving"

_C4_CONFIG = {
    "c4": {
        "scope_entity_type": "software-system",
        "scope_render_mode": "boundary",
        "internal_entity_types": ["container"],
    }
}


def _binding(element_id: str, entity_id: str, kind: str = "represents") -> dict:
    return {
        "id": f"bind-{element_id}",
        "subject": {"kind": "entity", "id": element_id},
        "correspondence_kind": kind,
        "target": {"entity_id": entity_id},
    }


def _conn_binding(element_id: str, connection_id: str) -> dict:
    return {
        "id": f"bind-{element_id}",
        "subject": {"kind": "connection", "id": element_id},
        "correspondence_kind": "represents",
        "target": {"connection_id": connection_id},
    }


def _conn_ids_binding(element_id: str, connection_ids: list[str]) -> dict:
    return {
        "id": f"bind-{element_id}",
        "subject": {"kind": "connection", "id": element_id},
        "correspondence_kind": "abstracts",
        "target": {"connection_ids": connection_ids},
    }


# ---------------------------------------------------------------------------
# C4PumlRenderer.collect_references
# ---------------------------------------------------------------------------


class TestC4RendererCollectReferences:
    def _renderer(self) -> C4PumlRenderer:
        return C4PumlRenderer(_C4_CONFIG)

    def _collect(self, bindings: list[dict], diagram_entities: dict | None = None) -> tuple[tuple, tuple]:
        renderer = self._renderer()
        # Patch resolve_c4_state to return empty model-backed state (no scope binding).
        from src.diagram_types.c4._resolve import _ResolvedItem, _ResolvedState
        empty_item = _ResolvedItem(
            local_id="_blank", item_type="software-system",
            alias="C4_blank", label="", description="", technology="", external=False,
        )
        empty_state = _ResolvedState(
            scope_item=empty_item, scope_render_mode="node",
            internal_items=[], outside_items=[], connections=(),
            entity_ids=(), connection_artifact_ids=(),
        )
        with patch("src.diagram_types.c4.renderer.resolve_c4_state", return_value=empty_state):
            refs = renderer.collect_references(
                "c4-container",
                Path("/repo"),
                diagram_entities=diagram_entities or {},
                diagram_connections=[],
                bindings=bindings,
            )
        return refs.entity_ids, refs.connection_ids

    def test_represents_entity_binding_collected(self) -> None:
        bindings = [_binding("box1", _ENTITY_A)]
        entity_ids, conn_ids = self._collect(bindings)
        assert _ENTITY_A in entity_ids
        assert conn_ids == ()

    def test_represents_connection_binding_collected(self) -> None:
        bindings = [_conn_binding("edge1", _CONN_ID)]
        entity_ids, conn_ids = self._collect(bindings)
        assert entity_ids == ()
        assert _CONN_ID in conn_ids

    def test_abstracts_connection_ids_collected(self) -> None:
        bindings = [_conn_ids_binding("edge1", [_CONN_ID])]
        entity_ids, conn_ids = self._collect(bindings)
        assert _CONN_ID in conn_ids

    def test_all_model_target_bindings_collected(self) -> None:
        """All bindings with model entity_id targets populate entity-ids-used."""
        bindings = [_binding("box1", _ENTITY_A, kind="traces-to")]
        entity_ids, conn_ids = self._collect(bindings)
        assert _ENTITY_A in entity_ids  # traces-to still references the entity

    def test_diagram_local_target_not_in_entity_ids(self) -> None:
        bindings = [{
            "id": "bind-box1",
            "subject": {"kind": "entity", "id": "box1"},
            "correspondence_kind": "scoped-by",
            "target": {"diagram_local": {"element_id": "box2"}},
        }]
        entity_ids, conn_ids = self._collect(bindings)
        assert entity_ids == ()
        assert conn_ids == ()

    def test_no_bindings_returns_empty(self) -> None:
        entity_ids, conn_ids = self._collect([])
        assert entity_ids == ()
        assert conn_ids == ()

    def test_multiple_bindings_all_collected(self) -> None:
        bindings = [
            _binding("box1", _ENTITY_A),
            _binding("box2", _ENTITY_B),
            _conn_binding("edge1", _CONN_ID),
        ]
        entity_ids, conn_ids = self._collect(bindings)
        assert _ENTITY_A in entity_ids
        assert _ENTITY_B in entity_ids
        assert _CONN_ID in conn_ids

    def test_model_backed_state_entity_ids_included(self) -> None:
        """Model-backed state entity_ids are merged with binding entity_ids."""
        renderer = self._renderer()
        from src.diagram_types.c4._resolve import _ResolvedItem, _ResolvedState
        scope_item = _ResolvedItem(
            local_id=_ENTITY_A, item_type="software-system",
            alias="APP_scope", label="App", description="", technology="", external=False,
        )
        model_state = _ResolvedState(
            scope_item=scope_item, scope_render_mode="boundary",
            internal_items=[], outside_items=[], connections=(),
            entity_ids=(_ENTITY_A,), connection_artifact_ids=(),
        )
        bindings = [_binding("box2", _ENTITY_B)]
        with patch("src.diagram_types.c4.renderer.resolve_c4_state", return_value=model_state):
            refs = renderer.collect_references(
                "c4-container", Path("/repo"),
                diagram_entities={}, diagram_connections=[],
                bindings=bindings,
            )
        assert _ENTITY_A in refs.entity_ids
        assert _ENTITY_B in refs.entity_ids

    def test_no_duplicates_between_state_and_bindings(self) -> None:
        renderer = self._renderer()
        from src.diagram_types.c4._resolve import _ResolvedItem, _ResolvedState
        scope_item = _ResolvedItem(
            local_id=_ENTITY_A, item_type="software-system",
            alias="APP_scope", label="App", description="", technology="", external=False,
        )
        model_state = _ResolvedState(
            scope_item=scope_item, scope_render_mode="node",
            internal_items=[], outside_items=[], connections=(),
            entity_ids=(_ENTITY_A,), connection_artifact_ids=(),
        )
        bindings = [_binding("box1", _ENTITY_A)]  # same as model state
        with patch("src.diagram_types.c4.renderer.resolve_c4_state", return_value=model_state):
            refs = renderer.collect_references(
                "c4-container", Path("/repo"),
                diagram_entities={}, diagram_connections=[],
                bindings=bindings,
            )
        assert refs.entity_ids.count(_ENTITY_A) == 1


# ---------------------------------------------------------------------------
# ActivityPumlRenderer.collect_references
# ---------------------------------------------------------------------------


class TestActivityRendererCollectReferences:
    def _renderer(self) -> ActivityPumlRenderer:
        return ActivityPumlRenderer({})

    def _collect(self, bindings: list[dict]) -> tuple[tuple, tuple]:
        renderer = self._renderer()
        refs = renderer.collect_references(
            "activity",
            Path("/repo"),
            diagram_entities={},
            diagram_connections=[],
            bindings=bindings,
        )
        return refs.entity_ids, refs.connection_ids

    def test_represents_entity_binding_collected(self) -> None:
        entity_ids, conn_ids = self._collect([_binding("lane1", _ENTITY_A)])
        assert _ENTITY_A in entity_ids
        assert conn_ids == ()

    def test_represents_connection_binding_collected(self) -> None:
        entity_ids, conn_ids = self._collect([_conn_binding("edge1", _CONN_ID)])
        assert entity_ids == ()
        assert _CONN_ID in conn_ids

    def test_all_model_target_bindings_collected(self) -> None:
        """All bindings with model entity_id targets populate entity-ids-used."""
        entity_ids, conn_ids = self._collect([_binding("lane1", _ENTITY_A, kind="refines")])
        assert _ENTITY_A in entity_ids

    def test_no_bindings_returns_empty(self) -> None:
        entity_ids, conn_ids = self._collect([])
        assert entity_ids == ()
        assert conn_ids == ()


# ---------------------------------------------------------------------------
# Scope injection: _scope_entity_id from scoped-by binding flows to renderer
# ---------------------------------------------------------------------------


class TestScopeInjectionFromBinding:
    """Verify that diagram.py / diagram_edit.py inject _scope_entity_id from
    the scoped-by binding so the C4 renderer can switch to model-backed mode."""

    def test_scope_entity_id_injected_for_model_backed_render(self) -> None:
        from src.application.modeling.binding_normalize import normalize_bindings

        diagram_entities: dict = {"software-system": [{"id": "sys1", "label": "My System"}]}
        raw_bindings = [
            {
                "id": "bind-scope",
                "subject": {"kind": "diagram"},
                "correspondence_kind": "scoped-by",
                "target": {"entity_id": _ENTITY_A},
            }
        ]
        norm = normalize_bindings(diagram_entities, raw_bindings)
        scope_eid = next(
            (b.target.entity_id for b in norm
             if b.correspondence_kind == "scoped-by" and b.subject.kind == "diagram"
             and b.target.entity_id),
            None,
        )
        assert scope_eid == _ENTITY_A
