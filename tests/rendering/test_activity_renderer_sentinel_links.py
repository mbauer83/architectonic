from __future__ import annotations

from pathlib import Path

from src.diagram_types.activity.renderer import ActivityPumlRenderer


def _render(diagram_entities: object, diagram_connections: list[dict[str, object]] | None = None) -> str:
    return ActivityPumlRenderer({}).render_body(
        "Flow", [], [], "activity", Path("/tmp"),
        diagram_entities=diagram_entities, diagram_connections=diagram_connections,
    )


def test_action_sentinel_wraps_the_label_as_an_invisible_anchor() -> None:
    # The label itself is the anchor ([[url label]]) — no separate visible "arch://…" link
    # text inside the shape; the preamble styles hyperlinks as plain text.
    puml = _render({"action": [
        {"type": "action", "id": "a1", "label": "Ship Order", "entity_id": "APC@1.orders"},
    ]})
    assert ":[[arch://APC@1.orders Ship Order]];" in puml
    assert "Ship Order [[arch://" not in puml


def test_action_sentinel_falls_back_to_local_id_when_unbound() -> None:
    puml = _render({"action": [{"type": "action", "id": "a1", "label": "Ship Order"}]})
    assert ":[[arch://a1 Ship Order]];" in puml


def test_action_preserves_user_link_alongside_sentinel() -> None:
    puml = _render({"action": [
        {"type": "action", "id": "a1", "label": "Go", "link": "https://example.com/docs",
         "entity_id": "APC@1.orders"},
    ]})
    assert ":[[arch://APC@1.orders Go]] [[https://example.com/docs]];" in puml


def test_decision_sentinel_in_condition_line() -> None:
    puml = _render({"decision": [
        {"type": "decision", "id": "d1", "condition": "Valid", "then_label": "yes", "else_label": "no",
         "entity_id": "GRF@1.gate"},
    ]})
    assert "if ([[arch://GRF@1.gate Valid?]]) then (yes)" in puml


def test_decision_sentinel_falls_back_to_local_id_when_unbound() -> None:
    puml = _render({"decision": [
        {"type": "decision", "id": "d1", "condition": "Valid", "then_label": "yes", "else_label": "no"},
    ]})
    assert "if ([[arch://d1 Valid?]]) then (yes)" in puml


def test_partition_sentinel_after_label() -> None:
    puml = _render({"partition": [{"type": "partition", "id": "p1", "label": "Phase 1"}]})
    assert 'partition "Phase 1" [[arch://p1]] {' in puml


def test_fork_emits_no_link_syntax() -> None:
    """PlantUML's `fork` keyword takes no label/link argument (`fork [[url]]` is a syntax
    error) — verified against a real render; forks stay unselectable in the viewer."""
    puml = _render(
        {
            "fork": [{"type": "fork", "id": "f1", "entity_id": "APC@1.orders"}],
            "action": [
                {"type": "action", "id": "a1", "label": "Branch A"},
                {"type": "action", "id": "a2", "label": "Branch B"},
            ],
        },
        diagram_connections=[
            {"id": "c1", "conn_type": "step-fork-branch", "source": "f1", "target": "a1"},
            {"id": "c2", "conn_type": "step-fork-branch", "source": "f1", "target": "a2"},
        ],
    )
    # No trailing " [[...]]" was appended to the `fork` line itself — if it had been, this
    # exact substring (fork immediately followed by a newline) would not be found.
    assert "fork\n" in puml
    assert ":[[arch://a1 Branch A]];" in puml


def test_hyperlinks_styled_as_plain_text_in_preamble() -> None:
    puml = _render({"action": [{"type": "action", "id": "a1", "label": "Go"}]})
    assert "skinparam hyperlinkColor #252327" in puml
    assert "skinparam hyperlinkUnderline false" in puml
