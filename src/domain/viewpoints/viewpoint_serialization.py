"""Serialize viewpoint definitions back to the ``viewpoints: [ {slug, version, ...} ]``
mapping shape (Appendix-A canonical form): field defaults are omitted on write, and
``purpose``/``content`` write the singular-string shorthand for a one-element tuple.

The counterpart to ``viewpoint_parsing.py``: a definition edited through a GUI form or an
MCP tool call is a plain value object like any other, and must round-trip back to the
``.arch-repo/viewpoints.yaml`` text a repo-load reads — the same primitive both the
declarative starter library and any future authoring surface share, not a dead end that
only static hand-written YAML can produce.
"""

from __future__ import annotations

from typing import Any

from src.domain.concept_scope import ConceptScope
from src.domain.viewpoints.viewpoint_presentation_serialization import presentation_to_mapping
from src.domain.viewpoints.viewpoint_query_serialization import query_to_mapping
from src.domain.viewpoints.viewpoints import ViewpointCatalog, ViewpointDefinition


def _scope_to_mapping(scope: ConceptScope) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if scope.entity_types is not None:
        result["entity_types"] = sorted(scope.entity_types)
    if scope.connection_types is not None:
        result["connection_types"] = sorted(scope.connection_types)
    if scope.excluded_entity_types:
        result["excluded_entity_types"] = sorted(scope.excluded_entity_types)
    excluded_domains = {
        value for predicate in scope.excluded_hierarchy_predicates if predicate.index == 0 for value in predicate.values
    }
    if excluded_domains:
        result["excluded_domains"] = sorted(excluded_domains)
    if scope.excluded_connection_types:
        result["excluded_connection_types"] = sorted(scope.excluded_connection_types)
    return result


def _tuple_shorthand(values: tuple[str, ...]) -> str | list[str]:
    return values[0] if len(values) == 1 else list(values)


def viewpoint_definition_to_mapping(definition: ViewpointDefinition) -> dict[str, Any]:
    """Serialize one definition to the plain-mapping shape ``viewpoint_parsing.py`` reads."""
    result: dict[str, Any] = {
        "slug": definition.slug,
        "version": definition.version,
        "name": definition.name,
        "purpose": _tuple_shorthand(definition.purpose),
        "content": _tuple_shorthand(definition.content),
    }
    if definition.description:
        result["description"] = definition.description
    if definition.rationale:
        result["rationale"] = definition.rationale
    if definition.stakeholders:
        result["stakeholders"] = list(definition.stakeholders)
    if definition.concerns:
        result["concerns"] = list(definition.concerns)
    scope = _scope_to_mapping(definition.scope)
    if scope:
        result["scope"] = scope
    if definition.representation_types:
        result["representation_types"] = list(definition.representation_types)
    if definition.derivation_defaults:
        result["derivation_defaults"] = dict(definition.derivation_defaults)
    if definition.query is not None:
        result["query"] = query_to_mapping(definition.query)
    if definition.presentation is not None:
        result["presentation"] = presentation_to_mapping(definition.presentation)
    if definition.selection_mode is not None:
        result["selection_mode"] = definition.selection_mode
    if definition.forked_from is not None:
        lineage: dict[str, Any] = {
            "slug": definition.forked_from.slug,
            "version": definition.forked_from.version,
            "definition_digest": definition.forked_from.definition_digest,
        }
        if definition.forked_from.index_generation is not None:
            lineage["index_generation"] = definition.forked_from.index_generation
        result["forked_from"] = lineage
    return result


def viewpoint_catalog_to_mapping(catalog: ViewpointCatalog) -> dict[str, Any]:
    """Serialize a whole catalog to the ``{"viewpoints": [...]}`` YAML-writable shape."""
    return {"viewpoints": [viewpoint_definition_to_mapping(entry) for entry in catalog.entries]}
