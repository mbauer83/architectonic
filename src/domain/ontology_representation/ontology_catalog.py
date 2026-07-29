"""Ontology catalog utilities.

Registry-backed functions were removed in WU-05 (hexagonal conformance).
All registry data is now available via OntologyCatalog / ConnectionSemantics /
DiagramTypeCatalog (see src/domain/modules/catalogs.py) injected from the composition root.
Pure utility functions remain here.
"""

from __future__ import annotations


def format_entity_type_term(term: str) -> str:
    if term == "@all":
        return "entity"
    normalized = term[1:] if term.startswith("@") else term
    return normalized.replace("-", " ").replace("_", " ")
