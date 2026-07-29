"""Predicate for conditional module registration based on settings overrides."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def is_module_enabled(
    module: Any,
    overrides: dict[str, dict[str, object]],
    registered_names: set[str],
) -> bool:
    """Return True if *module* should be registered given YAML overrides and satisfied deps.

    Uses getattr with defaults so modules that don't declare enabled/requires are
    treated as always-enabled with no dependencies (backward-compatible).
    """
    module_name: str = str(module.name)
    effective_enabled: bool = bool(getattr(module, "enabled", True))

    yaml_entry = overrides.get(module_name, {})
    if "enabled" in yaml_entry:
        effective_enabled = bool(yaml_entry["enabled"])

    if not effective_enabled:
        return False

    requires: list[str] = list(getattr(module, "requires", []))
    for dep in requires:
        if dep not in registered_names:
            logger.warning(
                "Module %r skipped: required capability/module %r is not available",
                module_name,
                dep,
            )
            return False

    return True
