"""Tests for the ``assurance.neighbors_*`` traversal-budget settings: defaults,
configured values, and the hard clamps that keep misconfiguration from
unbounding the traversal."""

from __future__ import annotations

import pytest

from src.config.assurance_settings import (
    assurance_neighbors_default_max_hops,
    assurance_neighbors_max_edges,
    assurance_neighbors_max_hops,
    assurance_neighbors_max_nodes,
    assurance_neighbors_time_budget_seconds,
)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "load_settings", lambda: {"assurance": {}})
    assert assurance_neighbors_default_max_hops() == 1
    assert assurance_neighbors_max_hops() == 4
    assert assurance_neighbors_max_nodes() == 150
    assert assurance_neighbors_max_edges() == 300
    assert assurance_neighbors_time_budget_seconds() == 2.0


def test_reads_configured_values(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(
        settings,
        "load_settings",
        lambda: {
            "assurance": {
                "neighbors_default_max_hops": 2,
                "neighbors_max_hops": 3,
                "neighbors_max_nodes": 50,
                "neighbors_max_edges": 80,
                "neighbors_time_budget_seconds": 0.5,
            },
        },
    )
    assert assurance_neighbors_default_max_hops() == 2
    assert assurance_neighbors_max_hops() == 3
    assert assurance_neighbors_max_nodes() == 50
    assert assurance_neighbors_max_edges() == 80
    assert assurance_neighbors_time_budget_seconds() == 0.5


def test_hard_clamps_bound_misconfiguration(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(
        settings,
        "load_settings",
        lambda: {
            "assurance": {
                "neighbors_default_max_hops": 99,
                "neighbors_max_hops": 99,
                "neighbors_max_nodes": 10**9,
                "neighbors_max_edges": 10**9,
                "neighbors_time_budget_seconds": -3,
            },
        },
    )
    assert assurance_neighbors_default_max_hops() == 4
    assert assurance_neighbors_max_hops() == 4
    assert assurance_neighbors_max_nodes() == 1000
    assert assurance_neighbors_max_edges() == 2000
    assert assurance_neighbors_time_budget_seconds() == 0.1


def test_garbage_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(
        settings,
        "load_settings",
        lambda: {
            "assurance": {
                "neighbors_max_hops": "not-a-number",
                "neighbors_max_nodes": None,
                "neighbors_time_budget_seconds": "soon",
            },
        },
    )
    assert assurance_neighbors_max_hops() == 4
    assert assurance_neighbors_max_nodes() == 150
    assert assurance_neighbors_time_budget_seconds() == 2.0


def test_non_dict_section_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "load_settings", lambda: {"assurance": "oops"})
    assert assurance_neighbors_default_max_hops() == 1
    assert assurance_neighbors_max_nodes() == 150
