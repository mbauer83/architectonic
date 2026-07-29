"""
Regression tests for C4 person-node rendering (WU-E1 + WU-E2 + WU-E7).

WU-E1/E2 root cause: `actor` keyword places label text *below* the stick figure on the
white canvas background with FontColor white → white-on-white, invisible.
WU-E7 fix: switch to C4-PlantUML stdlib Person/Person_Ext macros — person glyph + coloured
box, rendering the label inside the box, not as invisible text below the figure.
"""
from __future__ import annotations

from pathlib import Path

from src.diagram_types.c4._resolve import _ResolvedItem
from src.diagram_types.c4.renderer import C4PumlRenderer

# ── helpers ────────────────────────────────────────────────────────────────────

def _person(*, label: str, alias: str, external: bool = False) -> _ResolvedItem:
    return _ResolvedItem(
        local_id="p1",
        item_type="person",
        alias=alias,
        label=label,
        description="",
        technology="",
        external=external,
    )


def _renderer_standalone() -> C4PumlRenderer:
    return C4PumlRenderer(
        {
            "c4": {
                "scope_entity_type": "software-system",
                "scope_render_mode": "node",
                "internal_entity_types": [],
            }
        }
    )


def _render_standalone_with_person(person_label: str, external: bool = False) -> str:
    """Render a standalone C4 diagram with a single explicit person entity."""
    renderer = _renderer_standalone()
    diagram_entities = {
        "software-system": [{"id": "sys1", "label": "My System", "scope": True}],
        "person": [{"id": "p1", "label": person_label, "external": external}],
    }
    return renderer.render_body(
        "Test Diagram",
        [],
        [],
        "c4-system-context",
        Path("/tmp"),
        diagram_entities=diagram_entities,
    )


# ── tests ──────────────────────────────────────────────────────────────────────

def test_internal_person_emits_person_macro_not_actor() -> None:
    """Internal person → Person macro (C4 stdlib); never 'actor' keyword."""
    puml = _render_standalone_with_person("Architect", external=False)
    assert "actor" not in puml
    assert 'Person(P_p1_0, "Architect")' in puml


def test_external_person_emits_person_ext_macro() -> None:
    """External person → Person_Ext macro (C4 stdlib)."""
    puml = _render_standalone_with_person("External User", external=True)
    assert "actor" not in puml
    assert 'Person_Ext(P_p1_0, "External User")' in puml


def test_stdlib_include_present_for_person_shapes() -> None:
    """C4-PlantUML stdlib include must be in the PUML so Person macro resolves."""
    puml = _render_standalone_with_person("User")
    assert "!include <C4/C4_Component>" in puml
    assert "skinparam actor" not in puml


def test_person_label_name_appears_in_puml() -> None:
    """The person's name must appear verbatim in the PUML output."""
    puml = _render_standalone_with_person("Alice")
    assert "Alice" in puml


def test_person_with_description_still_uses_person_macro() -> None:
    """Even when a description is attached, person nodes must use Person macro not actor."""
    renderer = _renderer_standalone()
    diagram_entities = {
        "software-system": [{"id": "sys1", "label": "System", "scope": True}],
        "person": [{"id": "p1", "label": "Analyst", "description": "Performs hazard analysis"}],
    }
    puml = renderer.render_body(
        "Test",
        [],
        [],
        "c4-system-context",
        Path("/tmp"),
        diagram_entities=diagram_entities,
    )
    assert "actor" not in puml
    assert "Analyst" in puml
    assert 'Person(' in puml


def test_render_item_person_direct() -> None:
    """Unit test _render_item directly for a person item."""
    renderer = _renderer_standalone()
    internal = _person(label="Architect", alias="ACT_x", external=False)
    external = _person(label="Partner", alias="ACT_y", external=True)

    assert 'Person(ACT_x, "Architect")' == renderer._render_item(internal)
    assert 'Person_Ext(ACT_y, "Partner")' == renderer._render_item(external)
