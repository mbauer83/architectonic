"""Build executable selections from a viewpoint's declared concept scope, and classify
how a definition's two selection layers (scope and query) relate — the basis for the
``selection_mode`` routing, the informational divergence code, and the migration that
stamps a mode onto pre-change definitions."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from src.domain.concept_scope import ConceptScope
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    ConnectionSelection,
    EntityCriteriaGroup,
    ValueRef,
)
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, ViewpointDefinition


def definition_with_scope_query(definition: ViewpointDefinition) -> tuple[ViewpointDefinition, bool]:
    """Return a definition whose ACTIVE selection layer is executable as a query.

    ``selection_mode: scope`` routes through the scope-generated query even when a
    (then-inactive) query object is persisted — exactly one layer ever executes.
    ``selection_mode: query`` (and the pre-migration legacy default) executes the query
    when present; a definition with no query at all always falls back to its scope.
    """
    if definition.selection_mode == "scope":
        return replace(definition, query=query_from_scope(definition.scope)), True
    if definition.query is not None:
        return definition, False
    return replace(definition, query=query_from_scope(definition.scope)), True


SelectionLayerClass = Literal["scope-only", "query-only", "dual-equivalent", "dual-divergent"]


def classify_selection_layers(definition: ViewpointDefinition) -> SelectionLayerClass:
    """Mechanical relationship between a definition's two selection layers.

    ``dual-equivalent`` means the persisted query IS the scope's mechanical translation
    (`query_from_scope`) — nothing more expressive; anything else with both layers
    present is ``dual-divergent``. Divergence is a normal state (the author chose one
    mode and kept the other layer), never an error — but a divergent definition cannot
    be mode-stamped mechanically, because the two layers select different populations.
    """
    if definition.query is None:
        return "scope-only"
    if definition.scope == ConceptScope.unrestricted():
        return "query-only"
    return "dual-equivalent" if definition.query == query_from_scope(definition.scope) else "dual-divergent"


def query_from_scope(scope: ConceptScope) -> ExecutableViewpointQuery:
    """Translate type restrictions to criteria while retaining richer scope checks."""
    entity_criteria = EntityCriteriaGroup()
    if scope.entity_types is not None:
        entity_criteria = EntityCriteriaGroup(
            children=(
                AttributeCondition(
                    attribute="type",
                    comparator="in",
                    value=ValueRef(literal=sorted(scope.entity_types)),
                ),
            )
        )
    connections = ConnectionSelection()
    if scope.connection_types is not None:
        connections = ConnectionSelection(
            criteria=ConnectionCriteriaGroup(
                children=(
                    AttributeCondition(
                        attribute="type",
                        comparator="in",
                        value=ValueRef(literal=sorted(scope.connection_types)),
                    ),
                )
            )
        )
    return ExecutableViewpointQuery(entity_criteria=entity_criteria, connections=connections)
