"""Derivation package — view-derivation strategies and catalog.

Strategy modules are imported here for convenient access; the composition
root (app_bootstrap.py) registers them explicitly via DerivationStrategyCatalogBuilder.
"""

from __future__ import annotations

from src.application.derivation.strategy_registry import (
    DerivationStrategyCatalog,
    DerivationStrategyCatalogBuilder,
    StrategySpec,
)
from src.application.derivation.types import CandidateSet, DeriveFn, ModelQuery

from . import (  # noqa: F401
    explicit_selection,
    incident_connections,
    local_neighborhood,
    path_projection,
)

__all__ = [
    "CandidateSet",
    "DeriveFn",
    "DerivationStrategyCatalog",
    "DerivationStrategyCatalogBuilder",
    "ModelQuery",
    "StrategySpec",
    "explicit_selection",
    "incident_connections",
    "local_neighborhood",
    "path_projection",
]
