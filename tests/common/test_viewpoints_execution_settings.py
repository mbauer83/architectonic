"""Tests for the ``viewpoints.execution_*``/``derivation_*`` settings."""

from __future__ import annotations

import pytest

from src.config.viewpoints_settings import (
    viewpoints_derivation_max_hops,
    viewpoints_derivation_max_relationships,
    viewpoints_derivation_time_budget_seconds,
    viewpoints_execution_default_entity_limit_mcp,
    viewpoints_execution_max_entities,
    viewpoints_execution_timeout_seconds,
    viewpoints_max_derived_attributes,
    viewpoints_max_query_bindings,
    viewpoints_max_query_parameters,
)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "load_settings", lambda: {"viewpoints": {}})
    assert viewpoints_execution_max_entities() == 500
    assert viewpoints_execution_default_entity_limit_mcp() == 200
    assert viewpoints_execution_timeout_seconds() == 10.0
    assert viewpoints_max_query_bindings() == 8
    assert viewpoints_max_query_parameters() == 4
    assert viewpoints_max_derived_attributes() == 8
    assert viewpoints_derivation_max_hops() == 4
    assert viewpoints_derivation_max_relationships() == 20000
    assert viewpoints_derivation_time_budget_seconds() == 2.0


def test_reads_configured_values(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(
        settings,
        "load_settings",
        lambda: {
            "viewpoints": {
                "execution_max_entities": 50,
                "execution_default_entity_limit_mcp": 10,
                "execution_timeout_seconds": 2.5,
                "max_query_bindings": 3,
                "max_query_parameters": 2,
                "max_derived_attributes": 5,
                "derivation_max_hops": 6,
                "derivation_max_relationships": 100,
                "derivation_time_budget_seconds": 5.5,
            }
        },
    )
    assert viewpoints_execution_max_entities() == 50
    assert viewpoints_execution_default_entity_limit_mcp() == 10
    assert viewpoints_execution_timeout_seconds() == 2.5
    assert viewpoints_max_query_bindings() == 3
    assert viewpoints_max_query_parameters() == 2
    assert viewpoints_max_derived_attributes() == 5
    assert viewpoints_derivation_max_hops() == 6
    assert viewpoints_derivation_max_relationships() == 100
    assert viewpoints_derivation_time_budget_seconds() == 5.5


def test_invalid_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(
        settings,
        "load_settings",
        lambda: {
            "viewpoints": {
                "execution_max_entities": "not-a-number",
                "execution_default_entity_limit_mcp": "not-a-number",
                "execution_timeout_seconds": "not-a-number",
                "max_query_bindings": "not-a-number",
                "max_query_parameters": "not-a-number",
                "max_derived_attributes": "not-a-number",
                "derivation_max_hops": "not-a-number",
                "derivation_max_relationships": "not-a-number",
                "derivation_time_budget_seconds": "not-a-number",
            }
        },
    )
    assert viewpoints_execution_max_entities() == 500
    assert viewpoints_execution_default_entity_limit_mcp() == 200
    assert viewpoints_execution_timeout_seconds() == 10.0
    assert viewpoints_max_query_bindings() == 8
    assert viewpoints_max_query_parameters() == 4
    assert viewpoints_max_derived_attributes() == 8
    assert viewpoints_derivation_max_hops() == 4
    assert viewpoints_derivation_max_relationships() == 20000
    assert viewpoints_derivation_time_budget_seconds() == 2.0
