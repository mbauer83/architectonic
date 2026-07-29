from __future__ import annotations

import dataclasses
from pathlib import Path

from src.diagram_types.sequence.renderer import SequencePumlRenderer


class _FakeQuery:
    def __init__(self, entities: dict[str, object]) -> None:
        self._entities = entities

    def get_entity(self, artifact_id: str):
        return self._entities.get(artifact_id)


def _entity(entity_id: str, display_alias: str) -> object:
    from tests.application.derivation._fixtures import _entity as _make  # noqa: PLC0415

    e = _make(entity_id, "application-component")
    return dataclasses.replace(e, display_alias=display_alias)


def _ll(ll_id: str, label: str, entity_id: str | None = None) -> dict[str, object]:
    m: dict[str, object] = {"id": ll_id, "label": label}
    if entity_id:
        m["entity_id"] = entity_id
    return m


def _render(diagram_entities: object, monkeypatch, query: _FakeQuery) -> str:
    monkeypatch.setattr("src.infrastructure.artifact_index.shared_artifact_index", lambda roots: query)
    return SequencePumlRenderer({}).render_body(
        "Flow", [], [], "sequence", Path("/tmp"), diagram_entities=diagram_entities,
    )


def test_bound_lifeline_aliased_by_entity_display_alias(monkeypatch) -> None:
    query = _FakeQuery({"APC@1.orders": _entity("APC@1.orders", "App_Orders")})
    puml = _render(
        {"lifeline": [_ll("ll1", "Orders Service", "APC@1.orders")]},
        monkeypatch, query,
    )
    assert 'participant "Orders Service" as App_Orders' in puml
    assert "LL1" not in puml


def test_unbound_lifeline_falls_back_to_normalized_local_id(monkeypatch) -> None:
    query = _FakeQuery({})
    puml = _render({"lifeline": [_ll("ll1", "Anon")]}, monkeypatch, query)
    assert 'participant "Anon" as ll1' in puml


def test_bound_lifeline_with_unresolvable_entity_falls_back(monkeypatch) -> None:
    query = _FakeQuery({})
    puml = _render(
        {"lifeline": [_ll("ll1", "Ghost", "APC@1.missing")]},
        monkeypatch, query,
    )
    assert 'participant "Ghost" as ll1' in puml


def test_unbound_lifeline_normalizes_hyphenated_local_id(monkeypatch) -> None:
    query = _FakeQuery({})
    puml = _render({"lifeline": [_ll("ll-2026-abc", "Anon")]}, monkeypatch, query)
    assert 'participant "Anon" as ll_2026_abc' in puml


def test_bound_lifeline_normalizes_hyphenated_alias(monkeypatch) -> None:
    query = _FakeQuery({"APC@1.orders": _entity("APC@1.orders", "App-Orders")})
    puml = _render(
        {"lifeline": [_ll("ll1", "Orders Service", "APC@1.orders")]},
        monkeypatch, query,
    )
    assert 'participant "Orders Service" as App_Orders' in puml


def test_messages_reference_bound_lifeline_alias(monkeypatch) -> None:
    query = _FakeQuery({
        "APC@1.orders": _entity("APC@1.orders", "App_Orders"),
        "APC@1.payments": _entity("APC@1.payments", "App_Payments"),
    })
    diagram_entities = {
        "lifeline": [_ll("ll1", "Orders", "APC@1.orders"), _ll("ll2", "Payments", "APC@1.payments")],
        "message": [{"id": "m1", "label": "charge"}],
        "_connections": [
            {"id": "c1", "conn_type": "seq-from", "source": "m1", "target": "ll1"},
            {"id": "c2", "conn_type": "seq-to", "source": "m1", "target": "ll2"},
        ],
    }
    puml = _render(diagram_entities, monkeypatch, query)
    assert "App_Orders -> App_Payments: charge" in puml
