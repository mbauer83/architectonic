"""WU-1.1 acceptance: workspace entity ids allocated via the allocator.

Tests cover normalize_diagram_entity_identities directly (the core logic),
plus a static import guard confirming the write paths wire it in.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.application.identifier_allocator import DefaultIdentifierAllocator, get_default_allocator
from src.infrastructure.write.artifact_write.diagram_entity_identity import (
    normalize_diagram_entity_identities,
)


def _mock_catalog(prefix: str = "CLF", entity_type: str = "classifier"):
    ui_cfg = MagicMock()
    ui_cfg.identity_scope = "workspace"
    ui_cfg.id_prefix = prefix
    ui_cfg.entity_type = entity_type
    module = MagicMock()
    module.ui_config.diagram_only_types = [ui_cfg]
    catalog = MagicMock()
    catalog.find_diagram_type.return_value = module
    return catalog


# ---------------------------------------------------------------------------
# Core normalization
# ---------------------------------------------------------------------------


def test_missing_id_is_allocated() -> None:
    """An entity with no id gets a CLF@… id allocated."""
    entities, _, _ = normalize_diagram_entity_identities(
        "datatype",
        {"classifier": [{"id": "", "label": "Order"}]},
        [],
        [],
        module_catalog=_mock_catalog(),
        allocator=DefaultIdentifierAllocator(),
    )
    clf = entities["classifier"][0]
    assert clf["id"].startswith("CLF@"), f"Expected CLF@ prefix, got {clf['id']!r}"


def test_valid_id_preserved() -> None:
    """An entity with an already-valid CLF@ id is not modified."""
    valid_id = "CLF@1234567890.AbCd12.order"
    entities, _, _ = normalize_diagram_entity_identities(
        "datatype",
        {"classifier": [{"id": valid_id, "label": "Order"}]},
        [],
        [],
        module_catalog=_mock_catalog(),
        allocator=DefaultIdentifierAllocator(),
    )
    assert entities["classifier"][0]["id"] == valid_id


def test_connection_endpoints_rewritten() -> None:
    """Connection source/target are rewritten to the newly allocated id."""
    old_id = "temp-ref"
    entities, connections, _ = normalize_diagram_entity_identities(
        "datatype",
        {"classifier": [{"id": old_id, "label": "Order"}]},
        [{"id": "c1", "source": old_id, "target": "other"}],
        [],
        module_catalog=_mock_catalog(),
        allocator=DefaultIdentifierAllocator(),
    )
    new_id = entities["classifier"][0]["id"]
    assert connections[0]["source"] == new_id


def test_bindings_rewritten() -> None:
    """Binding references to old id are rewritten to the allocated id."""
    old_id = "temp-ref"
    entities, _, new_bindings = normalize_diagram_entity_identities(
        "datatype",
        {"classifier": [{"id": old_id}]},
        [],
        [{"subject": {"kind": "entity", "id": old_id}}],
        module_catalog=_mock_catalog(),
        allocator=DefaultIdentifierAllocator(),
    )
    new_id = entities["classifier"][0]["id"]
    assert new_bindings[0]["subject"]["id"] == new_id


def test_no_workspace_types_unchanged() -> None:
    """When the module has no workspace types, the payload is returned unchanged."""
    catalog = MagicMock()
    module = MagicMock()
    module.ui_config.diagram_only_types = []  # no workspace types
    catalog.find_diagram_type.return_value = module

    original = {"classifier": [{"id": "no-alloc"}]}
    entities, _, _ = normalize_diagram_entity_identities(
        "archimate", original, [], [],
        module_catalog=catalog,
        allocator=DefaultIdentifierAllocator(),
    )
    assert entities is original


# ---------------------------------------------------------------------------
# Default allocator sanity
# ---------------------------------------------------------------------------


def test_default_allocator_returns_valid_id() -> None:
    """get_default_allocator().allocate returns a prefix@... id."""
    allocator = get_default_allocator()
    result = allocator.allocate(prefix="CLF", name_hint="test")
    assert result.startswith("CLF@"), f"Expected CLF@ prefix, got {result!r}"


# ---------------------------------------------------------------------------
# Static import guard: write paths wire in normalization
# ---------------------------------------------------------------------------


def test_create_diagram_imports_normalizer() -> None:
    """diagram.py (create_diagram) references normalize_diagram_entity_identities."""
    src = (Path(__file__).parents[3] / "src/infrastructure/write/artifact_write/diagram.py").read_text()
    assert "normalize_diagram_entity_identities" in src


def test_edit_diagram_imports_normalizer() -> None:
    """diagram_edit.py (edit_diagram) references normalize_diagram_entity_identities."""
    src = (Path(__file__).parents[3] / "src/infrastructure/write/artifact_write/diagram_edit.py").read_text()
    assert "normalize_diagram_entity_identities" in src
