"""Predicates for entity type classification via the module catalog."""

from src.domain.modules.catalogs import OntologyCatalog
from src.domain.modules.module_catalog import ModuleCatalog
from src.domain.modules.module_types import EntityTypeName


def is_internal_entity_type(artifact_type: str, ontology: OntologyCatalog) -> bool:
    """Return True if artifact_type belongs to the 'internal' element class.

    Internal types (e.g. global-artifact-reference) are system-managed and must
    not be created or surfaced directly in user-facing entity lists.
    """
    return artifact_type in ontology.entity_types_with_class("internal")


def is_assurance_entity_type(artifact_type: str, module_catalog: ModuleCatalog) -> bool:
    """Return True if artifact_type belongs to an assurance-class ontology module.

    Assurance types (loss, hazard, UCA, etc.) are excluded from default model
    stats/catalogs — they live in the confidential assurance store, not in git
    files, so they should never appear in the architecture entity listing.
    """
    for om in module_catalog.all_ontologies().values():
        if om.module_class == "assurance" and EntityTypeName(artifact_type) in om.entity_types:
            return True
    return False
