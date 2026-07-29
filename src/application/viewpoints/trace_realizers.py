"""The registry-derived eligible realizer set for the branch-complete leaf check
(``endpoint: {registry: permitted-realizers-of-requirement}``).

A requirement's terminal obligation is covered when an incoming realization chain reaches ANY
element whose type is *permitted by the ontology* to realize a requirement — across every
family (common behavior, business, application, technology, physical, strategy, implementation/
migration) — MINUS motivation-only refiners (realization between motivation elements is
refinement, not implementation) and the junction/grouping structural helpers. Derived once per
execution from the aggregated permitted-relationship rules, so adding a family to the ontology
extends coverage with no code change.
"""

from __future__ import annotations

from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName

_REALIZATION = ConnectionTypeName("archimate-realization")
_REQUIREMENT = EntityTypeName("requirement")
_MOTIVATION_DOMAIN = "motivation"
_STRUCTURAL_HELPERS = frozenset({"and-junction", "or-junction", "grouping"})


def eligible_realizer_types(registries: ModuleCatalog) -> frozenset[str]:
    """Entity types that legitimately realize a requirement (the leaf endpoint set)."""
    permitted = registries.aggregated_permitted_relationships()
    type_infos = registries.all_entity_types()
    eligible: set[str] = set()
    for source_type, connection_type in permitted.by_target().get(_REQUIREMENT, ()):
        if connection_type != _REALIZATION:
            continue
        name = str(source_type)
        info = type_infos.get(source_type)
        domain = info.hierarchy[0] if info is not None and info.hierarchy else ""
        if domain == _MOTIVATION_DOMAIN or name in _STRUCTURAL_HELPERS:
            continue
        eligible.add(name)
    return frozenset(eligible)
