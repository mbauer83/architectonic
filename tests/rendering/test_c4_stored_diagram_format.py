"""Regression tests asserting stored C4 diagram PUML bodies use the new C4-PlantUML stdlib format.

The old renderer used skinparam-based actor styling (`skinparam actor { FontColor white }`)
which caused person labels to be invisible (white text on white background) and created
edge-anchoring gaps (actor element wider than the visible stick-figure due to long invisible
label text).  These were migrated via auto-sync on 2026-06-21.

These tests guard against the old format ever reappearing in a stored diagram.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── discovery ──────────────────────────────────────────────────────────────────

def _c4_puml_files() -> list[Path]:
    """Return all stored C4 diagram .puml files in engagement repositories.

    Recurse into subdirectories: group collections store diagrams under
    ``diagram-catalog/diagrams/<group>/`` (e.g. ``platform-core/``), so a flat
    one-level glob would silently match nothing and skip every assertion.
    """
    root = Path(__file__).parent.parent.parent  # workspace root
    files: list[Path] = []
    for diagrams_dir in root.rglob("diagram-catalog/diagrams"):
        for puml in diagrams_dir.rglob("*.puml"):
            text = puml.read_text(encoding="utf-8")
            if re.search(r"diagram-type:\s*c4-", text):
                files.append(puml)
    return sorted(files)


_C4_FILES = _c4_puml_files()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "c4_puml" in metafunc.fixturenames:
        metafunc.parametrize("c4_puml", _C4_FILES, ids=[p.name for p in _C4_FILES])


# ── format assertion tests ──────────────────────────────────────────────────────

def test_c4_stored_diagram_uses_stdlib_include(c4_puml: Path) -> None:
    """Every stored C4 diagram must include the C4-PlantUML stdlib, not skinparam hacks."""
    body = c4_puml.read_text(encoding="utf-8")
    # Extract PUML body (skip YAML frontmatter)
    puml_start = body.find("@startuml")
    puml_body = body[puml_start:] if puml_start != -1 else body
    assert "!include <C4/" in puml_body, (
        f"{c4_puml.name}: stored PUML must use '!include <C4/...>' (C4-PlantUML stdlib). "
        "Old skinparam-based format causes invisible person labels and edge-anchoring gaps."
    )


def test_c4_stored_diagram_no_skinparam_actor(c4_puml: Path) -> None:
    """Stored C4 diagrams must not use the old 'skinparam actor { FontColor white }' pattern.

    That pattern made person labels invisible on white diagram backgrounds.
    """
    body = c4_puml.read_text(encoding="utf-8")
    puml_start = body.find("@startuml")
    puml_body = body[puml_start:] if puml_start != -1 else body
    assert "skinparam actor" not in puml_body, (
        f"{c4_puml.name}: must not use 'skinparam actor' (old format — causes invisible labels). "
        "Use Person/Person_Ext macros from C4-PlantUML stdlib instead."
    )


def test_c4_stored_diagram_persons_use_person_macro(c4_puml: Path) -> None:
    """If the diagram contains person-type entities, they must use Person/Person_Ext macros.

    'actor \"label\" as alias' is the old format that anchors edges incorrectly.
    """
    body = c4_puml.read_text(encoding="utf-8")
    puml_start = body.find("@startuml")
    puml_body = body[puml_start:] if puml_start != -1 else body
    # Only check diagrams that actually have person entities
    if "Person(" not in puml_body and "Person_Ext(" not in puml_body:
        return  # no persons — skip
    # If persons are present via macros, no bare 'actor "..."' lines should exist
    bare_actor = re.search(r"^actor\s+\"", puml_body, re.MULTILINE)
    assert bare_actor is None, (
        f"{c4_puml.name}: person entities must use Person/Person_Ext macros, "
        "not bare 'actor \"...\"' syntax (old format — creates edge-anchoring gaps)."
    )


def test_c4_stored_diagram_no_embedded_description_in_labels(c4_puml: Path) -> None:
    r"""C4 macro label arguments must not embed descriptions via '\n'.

    Root cause of T22 divergence: the old model-backed renderer produced
    ``rectangle "Name\nDescription..." <<C4External>>`` for external nodes,
    embedding description text unconditionally.  Internal Component nodes did
    not include descriptions, creating an inconsistency across the two stored
    component diagrams.  The new renderer uses the show_node_descriptions flag
    uniformly; no stored PUML should carry the old embedded-newline pattern.
    """
    body = c4_puml.read_text(encoding="utf-8")
    puml_start = body.find("@startuml")
    puml_body = body[puml_start:] if puml_start != -1 else body
    # Match C4 macro calls where the label argument contains a literal \n
    embedded = re.search(
        r'(?:Component|System|Container|Person)\w*\([^,]+,\s*"[^"]*\\n[^"]*"',
        puml_body,
    )
    assert embedded is None, (
        f"{c4_puml.name}: C4 macro label must not embed a description via '\\n'. "
        "Old format: rectangle \"Name\\nDescription\" <<C4External>>. "
        "New format: System_Ext(alias, \"Name\") — description gated by show_node_descriptions."
    )
