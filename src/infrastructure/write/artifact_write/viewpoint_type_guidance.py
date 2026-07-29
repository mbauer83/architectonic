"""Compact viewpoint scope summary shared by viewpoint listing surfaces.

Viewpoint discovery/enumeration is served by ``artifact_query_viewpoint`` (action='list')
and the ``/api/viewpoints`` route — NOT by entity/diagram-type authoring guidance, which is
a separate concern. This module holds only the scope summariser those listing surfaces reuse.
"""

from __future__ import annotations

from src.domain.concept_scope import ConceptScope


def summarize_scope(scope: ConceptScope) -> dict[str, object]:
    """Compact scope summary for guidance/enumeration surfaces — not the full serialized
    ``ConceptScope`` grammar (class/hierarchy predicates, endpoint rules), just enough for an
    agent to judge applicability at a glance: whether the viewpoint is unrestricted, and if not,
    which entity/connection types it admits or excludes."""
    if scope == ConceptScope.unrestricted():
        return {"unrestricted": True}
    summary: dict[str, object] = {"unrestricted": False}
    if scope.entity_types is not None:
        summary["entity_types"] = sorted(str(t) for t in scope.entity_types)
    if scope.connection_types is not None:
        summary["connection_types"] = sorted(str(t) for t in scope.connection_types)
    if scope.excluded_entity_types:
        summary["excluded_entity_types"] = sorted(str(t) for t in scope.excluded_entity_types)
    excluded_domains = {
        value for predicate in scope.excluded_hierarchy_predicates if predicate.index == 0 for value in predicate.values
    }
    if excluded_domains:
        summary["excluded_domains"] = sorted(excluded_domains)
    if scope.excluded_connection_types:
        summary["excluded_connection_types"] = sorted(str(t) for t in scope.excluded_connection_types)
    return summary
