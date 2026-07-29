"""Serialize a ``query:`` block to its canonical form."""

from __future__ import annotations

from typing import Any

from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute, QueryBinding, QueryParameter
from src.domain.viewpoints.viewpoint_criteria import ConnectionCriteriaGroup, EntityCriteriaGroup
from src.domain.viewpoints.viewpoint_criteria_serialization import (
    connection_criteria_group_to_mapping,
    connection_selection_to_mapping,
    entity_criteria_group_to_mapping,
    neighbor_inclusion_to_mapping,
)
from src.domain.viewpoints.viewpoint_trace_pattern_serialization import trace_patterns_to_list
from src.domain.viewpoints.viewpoint_value_types import format_result_type
from src.domain.viewpoints.viewpoints import QUERY_SCHEMA_VERSION, ExecutableViewpointQuery


def query_to_mapping(query: ExecutableViewpointQuery) -> dict[str, Any]:
    result: dict[str, Any] = {
        "query_schema": QUERY_SCHEMA_VERSION,
        "entity_criteria": entity_criteria_group_to_mapping(query.entity_criteria),
    }
    if query.include_connected:
        result["include_connected"] = [neighbor_inclusion_to_mapping(i) for i in query.include_connected]
    connections = connection_selection_to_mapping(query.connections)
    if connections:
        result["connections"] = connections
    if query.repo_scope != "both":
        result["repo_scope"] = query.repo_scope
    if query.bindings:
        result["bindings"] = [_binding_to_mapping(item) for item in query.bindings]
    if query.parameters:
        result["parameters"] = [_parameter_to_mapping(item) for item in query.parameters]
    if query.derived:
        result["derived"] = [_derived_to_mapping(item) for item in query.derived]
    if query.trace_patterns.patterns:
        result["trace_patterns"] = trace_patterns_to_list(query.trace_patterns)
    return result


def _binding_to_mapping(binding: QueryBinding) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": binding.name,
        "result_type": format_result_type(binding.result_type),
    }
    if binding.select is not None:
        result["select"] = binding.select
    if isinstance(binding.criteria, EntityCriteriaGroup):
        result["criteria"] = entity_criteria_group_to_mapping(binding.criteria)
    elif isinstance(binding.criteria, ConnectionCriteriaGroup):
        result["criteria"] = connection_criteria_group_to_mapping(binding.criteria)
    if binding.project is not None:
        result["project"] = binding.project
    if binding.aggregate is not None:
        result["aggregate"] = binding.aggregate
    if binding.tuple_of:
        result["tuple"] = list(binding.tuple_of)
    if binding.include_in_result:
        result["include_in_result"] = True
    return result


def _parameter_to_mapping(parameter: QueryParameter) -> dict[str, Any]:
    result: dict[str, Any] = {"name": parameter.name, "type": parameter.value_type}
    if parameter.is_set_valued:
        result["cardinality"] = parameter.cardinality
        if parameter.allowed_values:
            result["allowed_values"] = list(parameter.allowed_values)
        result["min_items"] = parameter.min_items
    if not parameter.required:
        result["required"] = False
    default = parameter.default
    if default is not None:
        if parameter.is_set_valued and isinstance(default, (list, tuple)):
            result["default"] = list(default)
        else:
            result["default"] = default
    if parameter.description:
        result["description"] = parameter.description
    return result


def _derived_to_mapping(attribute: DerivedAttribute) -> dict[str, Any]:
    result: dict[str, Any] = {"name": attribute.name}
    if attribute.source == "security-signal":
        result["source"] = "security-signal"
        result["metric"] = attribute.metric
        return result
    if attribute.direction != "either":
        result["direction"] = attribute.direction
    if attribute.traversal != "direct":
        result["traversal"] = attribute.traversal
    if attribute.include_potential:
        result["include_potential"] = True
    if attribute.max_hops is not None:
        result["max_hops"] = attribute.max_hops
    if attribute.connection_criteria is not None:
        result["connection_criteria"] = connection_criteria_group_to_mapping(attribute.connection_criteria)
    if attribute.endpoint_criteria is not None:
        result["endpoint_criteria"] = entity_criteria_group_to_mapping(attribute.endpoint_criteria)
    if attribute.reduce != "count":
        result["reduce"] = attribute.reduce
    if attribute.of is not None:
        result["of"] = attribute.of
    return result
