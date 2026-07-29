"""Regression: code-generation must emit the complete vocabulary regardless of capabilities.

The frontend type unions are generated once and committed. They are decoded against every
payload the GUI might receive, so they must include the assurance vocabulary even when the
generating machine has no confidential store configured. Previously `build_module_registry`
gated the assurance ontology + diagram types on the runtime `confidential_store` capability,
so `tools/ontology/generate_types.py` produced a smaller file on a machine without the store than on
one with it — a CI drift failure. `complete_vocabulary=True` must register everything.
"""

from __future__ import annotations

import pytest

import src.infrastructure.app_bootstrap as app_bootstrap

_ASSURANCE_ENTITIES = {"control-action", "unsafe-control-action", "hazard"}
_ASSURANCE_DIAGRAMS = {"bowtie", "control-structure", "gsn", "uca-matrix"}


@pytest.fixture()
def no_confidential_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a machine (e.g. CI) where the confidential store is not available."""
    monkeypatch.setattr(app_bootstrap, "_inject_capability_sentinels", lambda _names: None)


def test_complete_vocabulary_includes_assurance_without_store(no_confidential_store: None) -> None:
    registry = app_bootstrap.build_module_registry(complete_vocabulary=True)
    entity_types = set(registry.all_entity_types())
    diagram_types = set(registry.all_diagram_types())

    assert _ASSURANCE_ENTITIES <= entity_types
    assert _ASSURANCE_DIAGRAMS <= diagram_types
    assert "assurance" in registry.domain_order()


def test_gated_registry_drops_assurance_without_store(no_confidential_store: None) -> None:
    registry = app_bootstrap.build_module_registry()
    entity_types = set(registry.all_entity_types())

    assert not (_ASSURANCE_ENTITIES & entity_types)
    assert "assurance" not in registry.domain_order()


def test_complete_vocabulary_is_a_superset_of_the_gated_registry(no_confidential_store: None) -> None:
    full = set(app_bootstrap.build_module_registry(complete_vocabulary=True).all_entity_types())
    gated = set(app_bootstrap.build_module_registry().all_entity_types())

    assert gated < full
