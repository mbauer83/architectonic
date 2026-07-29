"""Domain declaration for diagram-type module manifests.

A DiagramTypeModuleManifest is a pure-domain descriptor that a diagram-type
module publishes so the composition root can register its derivation strategies
without any module-level side effects.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.relationships.derivation_types import DeriveFn, StrategySpec


@dataclass(frozen=True)
class DiagramTypeModuleManifest:
    """Descriptor published by a diagram-type module at import time (no side effects).

    compatible_ontologies: tuple of ontology module ids this diagram type can operate over.
    ontology_role_mapping: per-ontology mapping of visual role → model entity type names.
        Absent roles are intentionally unmodelled (e.g. C4 grouping boxes).
        Full parameterisation of projection algorithms to use this mapping is a
        flagged follow-on (K2-followon).
    strategies: (StrategySpec, DeriveFn) pairs registered at the composition root.
    """

    id: str
    version: int
    compatible_ontologies: tuple[str, ...]
    ontology_role_mapping: Mapping[str, Mapping[str, tuple[str, ...]]]
    strategies: tuple[tuple["StrategySpec", "DeriveFn"], ...] = field(default_factory=tuple)
