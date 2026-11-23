"""Predicate for conditional module registration based on settings overrides."""

from __future__ import annotations

from typing import Any


def module_skip_reason(
    module: Any,
    overrides: dict[str, dict[str, object]],
    registered_names: set[str],
) -> str | None:
    """Return the reason registration is skipped, or None when the module is enabled.

    Uses getattr with defaults so modules that don't declare enabled/requires are
    treated as always-enabled with no dependencies (backward-compatible).
    """
    module_name: str = str(module.name)
    effective_enabled: bool = bool(getattr(module, "enabled", True))

    yaml_entry = overrides.get(module_name, {})
    if "enabled" in yaml_entry:
        effective_enabled = bool(yaml_entry["enabled"])

    if not effective_enabled:
        return "disabled"

    requires: list[str] = list(getattr(module, "requires", []))
    for dep in requires:
        if dep not in registered_names:
            return f"required capability/module {dep!r} is not available"

    return None
