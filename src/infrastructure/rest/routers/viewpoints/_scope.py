"""Resolves an optional ``viewpoint`` query param to its ``ConceptScope`` — narrowing the
entity/connection palette and picker by a chosen (not yet applied) viewpoint's scope,
alongside the diagram-type's own scope (WU-E5a). Companion plan §6.2's "effective
authoring scope = diagram-type scope ∩ applied viewpoint scope" extended here from
*applying* a viewpoint to a diagram to *choosing* one while authoring.
"""

from __future__ import annotations

from fastapi import HTTPException

from src.application.runtime_catalogs import RuntimeCatalogs
from src.domain.concept_scope import ConceptScope


def resolve_viewpoint_scope(viewpoint: str | None, catalogs: RuntimeCatalogs) -> ConceptScope | None:
    if viewpoint is None:
        return None
    definition = catalogs.viewpoints.get(viewpoint)
    if definition is None:
        raise HTTPException(404, f"Viewpoint not found: {viewpoint!r}")
    return definition.scope
