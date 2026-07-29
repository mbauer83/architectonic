"""Shared query-environment preparation for viewpoint execution and the
GUI projection entry point: scope resolution, parameter binding, binding
evaluation, the derived-attribute partition (graph vs security-signal), eager
evaluation/fetch, and anchor resolution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from src.application.viewpoints.parameter_binding import (
    anchor_entity_ids,
    bind_parameters,
    inactive_parameter_names,
)
from src.application.viewpoints.ports import RepositoryReadAccess, SignalAttributeCapability
from src.application.viewpoints.signal_attributes import fetch_and_merge_signal_attributes
from src.domain.viewpoints.viewpoint_binding_evaluation import (
    BindingEvaluationInput,
    evaluate_bindings,
    evaluate_derived_attributes,
)
from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_derived_attribute_deferral import partition_derived_attributes
from src.domain.viewpoints.viewpoint_evaluation_context import EvaluationEnvironment
from src.domain.viewpoints.viewpoint_scope_query import definition_with_scope_query
from src.domain.viewpoints.viewpoints import ViewpointDefinition


@dataclass(frozen=True)
class PreparedQueryEnvironment:
    executable_definition: ViewpointDefinition
    scope_derived: bool
    entity_candidates: frozenset[str]
    environment: EvaluationEnvironment
    deferred_derived: tuple[DerivedAttribute, ...]
    deferred_signal: tuple[DerivedAttribute, ...]
    anchor_ids: tuple[str, ...]
    signal_warning: str | None = None


def prepare_query_environment(
    definition: ViewpointDefinition,
    parameters: Mapping[str, object] | None,
    read_access: RepositoryReadAccess,
    registries: RegistrySnapshot,
    signal_capability: SignalAttributeCapability | None = None,
) -> PreparedQueryEnvironment:
    executable_definition, scope_derived = definition_with_scope_query(definition)
    assert executable_definition.query is not None
    query = executable_definition.query
    entity_ids = scoped_entity_ids(read_access, query.repo_scope)
    connection_ids = scoped_connection_ids(read_access, query.repo_scope)
    binding_input = BindingEvaluationInput(
        tuple(sorted(entity_ids)), tuple(sorted(connection_ids)), read_access, registries
    )
    resolved_parameters = bind_parameters(query, parameters, read_access)
    bindings = evaluate_bindings(query.bindings, parameters=resolved_parameters, input=binding_input)
    partition = partition_derived_attributes(query)
    environment = evaluate_derived_attributes(
        partition.eager_graph, tuple(sorted(entity_ids)), input=binding_input, environment=bindings.environment
    )
    # Criteria-referenced signal attributes decide membership, so they are
    # batch-fetched over the full scoped candidate set (one call).
    environment, signal_warning = fetch_and_merge_signal_attributes(
        signal_capability, partition.eager_signal, tuple(sorted(entity_ids)), environment,
    )
    # Conditions referencing an unsupplied optional parameter drop out of their conjunction
    # rather than excluding everything — stamped once here so every criteria tree evaluated
    # from this environment (population, neighbours, connections, styling) agrees.
    environment = replace(environment, inactive_parameters=inactive_parameter_names(query, parameters))
    return PreparedQueryEnvironment(
        executable_definition=executable_definition,
        scope_derived=scope_derived,
        entity_candidates=frozenset(entity_ids),
        environment=environment,
        deferred_derived=partition.deferred_graph,
        deferred_signal=partition.deferred_signal,
        anchor_ids=anchor_entity_ids(query, resolved_parameters),
        signal_warning=signal_warning,
    )


def scoped_entity_ids(read_access: RepositoryReadAccess, scope: str) -> set[str]:
    if scope == "enterprise":
        return read_access.enterprise_entity_ids()
    if scope == "engagement":
        return read_access.engagement_entity_ids()
    return read_access.entity_ids()


def scoped_connection_ids(read_access: RepositoryReadAccess, scope: str) -> set[str]:
    if scope == "enterprise":
        return read_access.enterprise_connection_ids()
    if scope == "engagement":
        return read_access.engagement_connection_ids()
    return read_access.connection_ids()
