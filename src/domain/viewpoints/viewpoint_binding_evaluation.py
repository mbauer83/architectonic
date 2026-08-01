"""Pure execution of query bindings and direct derived attributes. Batched
relationship-derived attribute evaluation (`traversal: derived`) lives in
`viewpoint_derived_relationship_batch.py` — kept out of this module because it needs to
call back into this one for the shared `BindingEvaluationInput`/reduction pieces, and a
domain evaluator importing its own batching helper back would be circular."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute, QueryBinding
from src.domain.viewpoints.viewpoint_condition_evaluation import read_attribute_value
from src.domain.viewpoints.viewpoint_condition_validation import CriteriaContext
from src.domain.viewpoints.viewpoint_criteria import ConnectionCriteriaGroup, EntityCriteriaGroup
from src.domain.viewpoints.viewpoint_criteria_evaluation import (
    direction_matches,
    evaluate_connection_criteria,
    evaluate_entity_criteria,
)
from src.domain.viewpoints.viewpoint_derived_value_reduction import reduce_values
from src.domain.viewpoints.viewpoint_evaluation_context import BindingEvaluationInput, EvaluationEnvironment
from src.domain.viewpoints.viewpoint_value_types import (
    ConnectionInstanceType,
    EntityInstanceType,
    OptionalType,
)


class BindingCardinalityError(ValueError):
    """A binding declared to yield one value yielded another number of them.

    The binding, what it declared and what it found are carried as fields, not only interpolated
    into the message: a caller has to know *which* binding's criteria to change, and recovering that
    by parsing the sentence is the shape this release spent its time removing.
    """

    def __init__(self, binding: str, expectation: str, found: int) -> None:
        super().__init__(f"binding {binding!r} requires {expectation} result, got {found}")
        self.binding = binding
        self.expectation = expectation
        self.found = found


@dataclass(frozen=True)
class BindingEvaluationResult:
    environment: EvaluationEnvironment


def evaluate_bindings(
    bindings: tuple[QueryBinding, ...], *, parameters: dict[str, object], input: BindingEvaluationInput
) -> BindingEvaluationResult:
    values: dict[str, object] = {}
    for binding in bindings:
        environment = EvaluationEnvironment(bindings=values, parameters=parameters)
        selected = _select(binding, input, environment)
        values[binding.name] = _materialize(binding, selected, input, environment)
    return BindingEvaluationResult(EvaluationEnvironment(bindings=values, parameters=parameters))


def evaluate_derived_attributes(
    attributes: tuple[DerivedAttribute, ...],
    entity_ids: tuple[str, ...],
    *,
    input: BindingEvaluationInput,
    environment: EvaluationEnvironment,
) -> EvaluationEnvironment:
    # Local import: `viewpoint_derived_relationship_batch` needs `BindingEvaluationInput`
    # from this module's own home (`viewpoint_evaluation_context`) and calls back into
    # nothing here, so a module-level import would be safe too — kept local anyway so this
    # file's own import graph stays obviously acyclic at a glance.
    from src.domain.viewpoints.viewpoint_derived_relationship_batch import (
        evaluate_relationship_derived_batch,  # noqa: PLC0415
    )

    values: dict[tuple[str, str], object] = dict(environment.derived_values)
    entities = {
        entity_id: entity
        for entity_id in entity_ids
        if (entity := input.read_access.get_entity(entity_id)) is not None
    }
    for attribute in attributes:
        if attribute.traversal == "derived":
            batch_values = evaluate_relationship_derived_batch(attribute, tuple(entities), input, environment)
            for entity_id, value in batch_values.items():
                values[(entity_id, attribute.name)] = value
            continue
        for entity_id, entity in entities.items():
            values[(entity_id, attribute.name)] = _evaluate_derived(attribute, entity, input, environment)
    return EvaluationEnvironment(
        bindings=environment.bindings, parameters=environment.parameters, derived_values=values
    )


def _select(
    binding: QueryBinding, input: BindingEvaluationInput, environment: EvaluationEnvironment
) -> tuple[EntityRecord | ConnectionRecord, ...]:
    if binding.select == "entities":
        if binding.criteria is not None and not isinstance(binding.criteria, EntityCriteriaGroup):
            raise AssertionError("entity binding requires entity criteria")
        selected = (
            item
            for item_id in sorted(input.entity_ids)
            if (item := input.read_access.get_entity(item_id)) is not None
            and (
                binding.criteria is None
                or evaluate_entity_criteria(
                    binding.criteria,
                    item,
                    read_access=input.read_access,
                    registries=input.registries,
                    environment=environment,
                ).matched
            )
        )
        return tuple(selected)
    if binding.select == "connections":
        if binding.criteria is not None and not isinstance(binding.criteria, ConnectionCriteriaGroup):
            raise AssertionError("connection binding requires connection criteria")
        selected_connections: list[ConnectionRecord] = []
        for item_id in sorted(input.connection_ids):
            item = input.read_access.get_connection(item_id)
            if item is None:
                continue
            if (
                binding.criteria is not None
                and not evaluate_connection_criteria(
                    binding.criteria,
                    item,
                    read_access=input.read_access,
                    registries=input.registries,
                    environment=environment,
                ).matched
            ):
                continue
            selected_connections.append(item)
        return tuple(selected_connections)
    return ()


def _materialize(
    binding: QueryBinding,
    selected: tuple[EntityRecord | ConnectionRecord, ...],
    input: BindingEvaluationInput,
    environment: EvaluationEnvironment,
) -> object:
    if binding.tuple_of:
        return tuple(environment.bindings[name] for name in binding.tuple_of)
    value: object = selected
    if isinstance(binding.result_type, (EntityInstanceType, ConnectionInstanceType)):
        value = _single(binding.name, selected, required=True)
    elif isinstance(binding.result_type, OptionalType):
        value = _single(binding.name, selected, required=False)
    if binding.project is not None:
        context = cast(CriteriaContext, "entity" if binding.select == "entities" else "connection")
        records = value if isinstance(value, tuple) else (value,)
        values = tuple(
            item
            for record in records
            if isinstance(record, (EntityRecord, ConnectionRecord))
            for item, present in (
                read_attribute_value(record, binding.project, context=context, environment=environment),
            )
            if present
        )
        value = values if isinstance(value, tuple) else (values[0] if values else None)
    if binding.aggregate is not None:
        value = reduce_values(value, binding.aggregate)
    return value


def _single(name: str, values: tuple[EntityRecord | ConnectionRecord, ...], *, required: bool) -> object:
    if len(values) == 1:
        return values[0]
    if not required and not values:
        return None
    expectation = "exactly one" if required else "zero or one"
    raise BindingCardinalityError(name, expectation, len(values))


def _evaluate_derived(
    attribute: DerivedAttribute,
    entity: EntityRecord,
    input: BindingEvaluationInput,
    environment: EvaluationEnvironment,
) -> object:
    """Direct traversal only — `traversal: derived` attributes are batched across every
    entity that needs them by `evaluate_relationship_derived_batch`, called once per
    attribute before this function is ever reached for that attribute."""
    values: list[object] = []
    count = 0
    for connection in input.read_access.find_connections_for(entity.artifact_id, direction="any"):
        if not direction_matches(connection, entity.artifact_id, attribute.direction, input.registries):
            continue
        if (
            attribute.connection_criteria is not None
            and not evaluate_connection_criteria(
                attribute.connection_criteria,
                connection,
                read_access=input.read_access,
                registries=input.registries,
                environment=environment,
            ).matched
        ):
            continue
        other_id = connection.target if connection.source == entity.artifact_id else connection.source
        endpoint = input.read_access.get_entity(other_id)
        if endpoint is None:
            continue
        if (
            attribute.endpoint_criteria is not None
            and not evaluate_entity_criteria(
                attribute.endpoint_criteria,
                endpoint,
                read_access=input.read_access,
                registries=input.registries,
                environment=environment,
            ).matched
        ):
            continue
        count += 1
        if attribute.of is not None:
            head, _, path = attribute.of.partition(".")
            record = connection if head == "connection" else endpoint
            context = cast(CriteriaContext, "connection" if head == "connection" else "entity")
            value, present = read_attribute_value(record, path, context=context, environment=environment)
            if present:
                values.append(value)
    return count if attribute.reduce == "count" else reduce_values(tuple(values), attribute.reduce)
