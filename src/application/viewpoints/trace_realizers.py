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


def structural_helper_types(registries: ModuleCatalog) -> frozenset[str]:
    """Types that stand for something else in a chain rather than realizing anything themselves.

    Read from the composition rules, not listed here: the type (or class) a rule names as the
    *intermediate* it passes a relationship through is a helper by that very declaration — a junction
    *is* the relationship it joins (`RJ3`), and a grouping's realization is its members' (`PDR12`).
    Naming "and-junction", "or-junction" and "grouping" in code was a second place for the same fact
    to be wrong, and could not follow an ontology that declares a different container.
    """
    named_types: set[str] = set()
    named_classes: set[str] = set()
    for module in registries.all_ontologies().values():
        for rule in module.derivation_rules:
            if rule.intermediate_artifact_type is not None:
                named_types.add(str(rule.intermediate_artifact_type))
            if rule.intermediate_class is not None:
                named_classes.add(str(rule.intermediate_class))
    for name, info in registries.all_entity_types().items():
        if named_classes and not named_classes.isdisjoint(info.classes):
            named_types.add(str(name))
    return frozenset(named_types)


def eligible_realizer_types(registries: ModuleCatalog) -> frozenset[str]:
    """Entity types that legitimately realize a requirement (the leaf endpoint set)."""
    permitted = registries.aggregated_permitted_relationships()
    type_infos = registries.all_entity_types()
    helpers = structural_helper_types(registries)
    eligible: set[str] = set()
    for source_type, connection_type in permitted.by_target().get(_REQUIREMENT, ()):
        if connection_type != _REALIZATION:
            continue
        name = str(source_type)
        info = type_infos.get(source_type)
        domain = info.hierarchy[0] if info is not None and info.hierarchy else ""
        if domain == _MOTIVATION_DOMAIN or name in helpers:
            continue
        eligible.add(name)
    return frozenset(eligible)
