"""The names an icon's `applies-to` may use: every entity type the product knows, and every specialization.

Model entity types come from the ontologies, the types a diagram hosts itself (C4's containers) from
the diagram types, and specializations from the specialization catalog. A name outside these is a
typo or a type that has since been retired; either way the icon applies to nothing under it.
"""

from __future__ import annotations

from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.icons.applicability import Applicability


def icon_applicability_names(catalogs: RuntimeCatalogs) -> frozenset[str]:
    return (
        frozenset(catalogs.ontology.all_entity_type_names())
        | {str(name) for name in catalogs.module_catalog.all_diagram_entity_types()}
        | {spec.slug for spec in catalogs.specializations.entries}
    )


def unknown_applicability_names(applies_to: Applicability, known: frozenset[str]) -> list[str]:
    return sorted(applies_to.names - known)
