"""Target-population classification for honest empty/degenerate results.

A result's entities fall into three classes against the definition's declared TARGET
population: targets (the substantive types the viewpoint is about), incidental
substantive content (in scope and populated, but not the target), and structural helpers
(junctions/groupings — connective tissue, never substantive content). The header can then
say exactly what is absent and what IS shown.

The target population is a PRESENTATION-level declaration. In scope mode it may be
derived mechanically from the ACTIVE scope (minus structural helpers); in query mode it
must be declared explicitly — an expressive query cannot generally be reduced to a type
set. When it is UNKNOWN, absence claims are SUPPRESSED entirely: a guessed absence claim
is exactly the false copy this classification exists to prevent.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.viewpoints.viewpoints import ViewpointDefinition


@dataclass(frozen=True)
class TargetPopulationSummary:
    """Counts a result header can render as true statements."""

    target_types: tuple[str, ...]
    target_count: int
    incidental_type_counts: Mapping[str, int]
    structural_count: int


def is_structural_helper(type_name: str, type_info: EntityTypeInfo | None) -> bool:
    """Junctions (by ontology class) and groupings (the composite helper type) are
    connective tissue — displayed, but never substantive content a view is "about"."""
    if type_info is not None and "junction" in type_info.classes:
        return True
    return type_name == "grouping"


def declared_target_types(
    definition: ViewpointDefinition, entity_type_infos: Mapping[str, EntityTypeInfo]
) -> tuple[str, ...] | None:
    """The definition's target population, or ``None`` when it is unknown.

    An explicit presentation-level ``target_types`` declaration always wins. Without
    one, only a definition whose ACTIVE selection is the scope can derive targets
    mechanically (its scope types minus structural helpers); a query-mode definition
    with no declaration has an UNKNOWN target population.
    """
    if definition.presentation is not None and definition.presentation.target_types is not None:
        return tuple(sorted(definition.presentation.target_types))
    scope_is_active = definition.selection_mode == "scope" or (
        definition.selection_mode is None and definition.query is None
    )
    if scope_is_active and definition.scope.entity_types is not None:
        return tuple(
            sorted(
                type_name
                for type_name in definition.scope.entity_types
                if not is_structural_helper(type_name, entity_type_infos.get(type_name))
            )
        )
    return None


def summarize_target_population(
    target_types: tuple[str, ...],
    result_entity_types: Iterable[str],
    entity_type_infos: Mapping[str, EntityTypeInfo],
) -> TargetPopulationSummary:
    targets = set(target_types)
    target_count = 0
    structural_count = 0
    incidental: Counter[str] = Counter()
    for type_name in result_entity_types:
        if type_name in targets:
            target_count += 1
        elif is_structural_helper(type_name, entity_type_infos.get(type_name)):
            structural_count += 1
        else:
            incidental[type_name] += 1
    return TargetPopulationSummary(
        target_types=tuple(sorted(targets)),
        target_count=target_count,
        incidental_type_counts=dict(sorted(incidental.items())),
        structural_count=structural_count,
    )
