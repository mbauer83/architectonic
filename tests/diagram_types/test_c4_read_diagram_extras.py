"""Tests for DiagramTypeModule.resolve_diagram_entities — scope injection from a scoped-by binding.

Model-backed C4 diagrams keep diagram-entities empty and store the scope entity in a
`scoped-by` binding.  The edit view needs _scope_entity_id in diagram_entities to know
the diagram is model-backed; this hook must inject it.

It used to be ``read_diagram_extras``, which is the hook for a kind's *own* keys — using it to
overwrite a field the read envelope declares is what kept that envelope open. The two jobs are two
hooks now, and this is the declared-field one: it returns the replacement, or None to keep what the
frontmatter said.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.diagram_types.c4._type import load_c4_diagram_type
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule


def _load_container_type() -> DiagramTypeModule:
    pkg = Path(__file__).parent.parent.parent / "src" / "diagram_types" / "c4" / "container"
    return load_c4_diagram_type(pkg)


@pytest.fixture
def c4_type() -> DiagramTypeModule:
    return _load_container_type()


# ── helpers ──────────────────────────────────────────────────────────────────

def _parsed(diagram_entities: dict, bindings: list | None = None) -> dict:
    fm: dict = {"diagram-entities": diagram_entities}
    if bindings is not None:
        fm["bindings"] = bindings
    return {"frontmatter": fm}


def _scoped_by(entity_id: str) -> list[dict]:
    return [
        {
            "id": "bind-scope",
            "subject": {"kind": "diagram"},
            "correspondence_kind": "scoped-by",
            "target": {"entity_id": entity_id},
        }
    ]


# ── tests ─────────────────────────────────────────────────────────────────────

def test_injects_scope_entity_id_from_binding(c4_type: DiagramTypeModule) -> None:
    """When diagram-entities is empty and a scoped-by binding exists, inject the scope id."""
    result = c4_type.resolve_diagram_entities(
        _parsed({}, bindings=_scoped_by("APP@1780783671.hkrdtm.architecture-management-platform")), {}
    )
    assert result["_scope_entity_id"] == "APP@1780783671.hkrdtm.architecture-management-platform"


def test_does_not_override_explicit_scope_entity_id(c4_type: DiagramTypeModule) -> None:
    """If _scope_entity_id is already set, bindings must not override it."""
    result = c4_type.resolve_diagram_entities(
        _parsed({"_scope_entity_id": "APP@explicit"}, bindings=_scoped_by("APP@from-binding")),
        {"_scope_entity_id": "APP@explicit"},
    )
    # None means "keep what the read already has", which is the explicit value.
    assert result is None


def test_returns_empty_when_no_scope_anywhere(c4_type: DiagramTypeModule) -> None:
    """No binding, no diagram-entities value → no injection and no diagram_entities key."""
    result = c4_type.resolve_diagram_entities(_parsed({}), {})
    assert result is None


def test_preserves_existing_diagram_entities_entries(c4_type: DiagramTypeModule) -> None:
    """Injection must not drop pre-existing keys in diagram-entities."""
    result = c4_type.resolve_diagram_entities(
        _parsed({"_excluded_entity_ids": ["E1"]}, bindings=_scoped_by("APP@scope")),
        {"_excluded_entity_ids": ["E1"], "_connections": [{"id": "c1"}]},
    )
    assert result is not None
    assert result["_scope_entity_id"] == "APP@scope"
    assert result["_excluded_entity_ids"] == ["E1"]
    # The caller's local connections survive. Rebuilding the mapping from the frontmatter dropped
    # them, so a model-backed C4 diagram lost its own edges on every read.
    assert result["_connections"] == [{"id": "c1"}]


def test_non_diagram_subject_binding_is_ignored(c4_type: DiagramTypeModule) -> None:
    """Only diagram-subject scoped-by bindings count; entity-subject bindings must be ignored."""
    bindings = [
        {
            "id": "bind-entity",
            "subject": {"kind": "entity", "entity_id": "X"},
            "correspondence_kind": "scoped-by",
            "target": {"entity_id": "APP@should-be-ignored"},
        }
    ]
    result = c4_type.resolve_diagram_entities(_parsed({}, bindings=bindings), {})
    assert result is None


def test_missing_bindings_key_does_not_error(c4_type: DiagramTypeModule) -> None:
    """Frontmatter without a bindings key is handled gracefully."""
    result = c4_type.resolve_diagram_entities({"frontmatter": {"diagram-entities": {}}}, {})
    assert result is None
