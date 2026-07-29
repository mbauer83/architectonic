"""``assurance.*`` settings accessors — deployment-pinned budgets for the
assurance neighbor traversal, with hard clamps so misconfiguration can never
unbound the traversal (the shared backend is protected even from bad settings).
"""

from __future__ import annotations

from src.config import settings

_MAX_HOPS_HARD_CLAMP = 4
_MAX_NODES_HARD_CLAMP = 1000
_MAX_EDGES_HARD_CLAMP = 2000


def _assurance_value(key: str) -> object:
    # Reads through the module (never `from ... import load_settings`) so tests
    # that monkeypatch `settings.load_settings` take effect here too.
    section = settings.load_settings().get("assurance", {})
    if not isinstance(section, dict):
        return settings._DEFAULTS["assurance"][key]  # type: ignore[index]
    return section.get(key, settings._DEFAULTS["assurance"][key])  # type: ignore[index]


def _bounded_integer(key: str, default: int, hard_clamp: int) -> int:
    value = _assurance_value(key)
    try:
        return min(hard_clamp, max(1, int(value)))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


def assurance_neighbors_default_max_hops() -> int:
    """Hop count used when a neighbors request does not specify ``max_hops``."""
    return _bounded_integer("neighbors_default_max_hops", 1, _MAX_HOPS_HARD_CLAMP)


def assurance_neighbors_max_hops() -> int:
    """Upper bound any request's ``max_hops`` is clamped to."""
    return _bounded_integer("neighbors_max_hops", 4, _MAX_HOPS_HARD_CLAMP)


def assurance_neighbors_max_nodes() -> int:
    """Node budget for one traversal response; hitting it yields a truncated result."""
    return _bounded_integer("neighbors_max_nodes", 150, _MAX_NODES_HARD_CLAMP)


def assurance_neighbors_max_edges() -> int:
    """Edge budget for one traversal response; hitting it yields a truncated result."""
    return _bounded_integer("neighbors_max_edges", 300, _MAX_EDGES_HARD_CLAMP)


def assurance_neighbors_time_budget_seconds() -> float:
    """Wall-clock budget for one traversal. Unlike the size budgets, exceeding it
    aborts the whole request with a typed retryable error and no partial graph —
    wall-clock truncation is not deterministic, so the two must never mix."""
    value = _assurance_value("neighbors_time_budget_seconds")
    try:
        return max(0.1, float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 2.0
