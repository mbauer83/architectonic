"""``viewpoints.*`` settings accessors — split out of ``settings.py`` to keep that module
under the project's per-file line limit; shares the same ``_DEFAULTS``/``load_settings``
every other settings group reads from.
"""

from __future__ import annotations

from src.config import settings


def _viewpoints_value(key: str) -> object:
    # Reads `settings.load_settings`/`settings._DEFAULTS` through the module (never
    # `from ... import load_settings`) so tests that monkeypatch `settings.load_settings`
    # still take effect here — a direct name import binds its own separate reference at
    # import time that a later `monkeypatch.setattr(settings, "load_settings", ...)` can't
    # reach.
    viewpoints = settings.load_settings().get("viewpoints", {})
    if not isinstance(viewpoints, dict):
        return settings._DEFAULTS["viewpoints"][key]  # type: ignore[index]
    return viewpoints.get(key, settings._DEFAULTS["viewpoints"][key])  # type: ignore[index]


def viewpoints_execution_max_entities() -> int:
    """Hard cap on entities in a viewpoint execution result, all transports. GUI/REST
    default to this cap; MCP defaults lower (see below)."""
    value = _viewpoints_value("execution_max_entities")
    try:
        return max(1, int(value))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 500


def viewpoints_execution_default_entity_limit_mcp() -> int:
    """MCP ``execute`` action default entity limit when no ``limit`` argument is given —
    smaller than the hard cap to protect agent context windows."""
    value = _viewpoints_value("execution_default_entity_limit_mcp")
    try:
        return max(1, int(value))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 200


def viewpoints_execution_timeout_seconds() -> float:
    """Wall-clock budget for one viewpoint execution before it fails as a typed timeout
    error rather than returning a partial result."""
    value = _viewpoints_value("execution_timeout_seconds")
    try:
        return max(0.1, float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 10.0


def _viewpoints_positive_integer(key: str, default: int) -> int:
    value = _viewpoints_value(key)
    try:
        return max(1, int(value))  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


def viewpoints_max_query_bindings() -> int:
    return _viewpoints_positive_integer("max_query_bindings", 8)


def viewpoints_max_query_parameters() -> int:
    """Maximum number of execution parameters in one viewpoint definition."""
    return _viewpoints_positive_integer("max_query_parameters", 4)


def viewpoints_max_derived_attributes() -> int:
    """Maximum number of item-scoped derived attributes in one viewpoint definition."""
    return _viewpoints_positive_integer("max_derived_attributes", 8)


def viewpoints_diagram_render_max_entities() -> int:
    """Pre-flight ceiling for the ad-hoc diagram representation: beyond this many
    entities PlantUML rendering degenerates (or fails outright), so the surface refuses
    with a friendly, actionable message instead of a renderer stack error."""
    return _viewpoints_positive_integer("diagram_render_max_entities", 250)


def viewpoints_legibility_budget() -> int:
    """Default node count above which an exploration result opens aggregated instead of
    flat — the deployment-wide default a definition's ``presentation.legibility_budget``
    overrides per viewpoint."""
    return _viewpoints_positive_integer("legibility_budget", 100)


def viewpoints_derivation_max_hops() -> int:
    """Maximum modeled-relationship hops used to derive a relationship."""
    return _viewpoints_positive_integer("derivation_max_hops", 4)


def viewpoints_derivation_max_relationships() -> int:
    """Hard memory-protection ceiling on derived relationships returned by one derivation
    request — the practical limit in normal use is `viewpoints_derivation_time_budget_seconds`;
    this should not realistically fire once that time budget is in place."""
    return _viewpoints_positive_integer("derivation_max_relationships", 20000)


def viewpoints_derivation_time_budget_seconds() -> float:
    """Wall-clock budget for one relationship-derivation search before it stops and returns
    a partial, `truncated` result rather than continuing — a multi-anchor query (e.g. every
    entity in a domain) can legitimately produce thousands of relationships in about a
    second of real work, so this reflects actual cost rather than an arbitrary count."""
    value = _viewpoints_value("derivation_time_budget_seconds")
    try:
        return max(0.1, float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 2.0
