"""Tests for deterministic binding execution and ValueRef resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_binding_evaluation import (
    BindingCardinalityError,
    BindingEvaluationInput,
    evaluate_bindings,
)
from src.domain.viewpoints.viewpoint_bindings import QueryBinding
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_criteria_evaluation import evaluate_entity_criteria
from src.domain.viewpoints.viewpoint_value_types import EntityInstanceType, EntitySetType, OptionalType, ScalarType


def _entity(identifier: str, *, score: int = 0) -> EntityRecord:
    return EntityRecord(
        artifact_id=identifier,
        artifact_type="component",
        name=identifier,
        version="1",
        status="draft",
        domain="application",
        subdomain="components",
        path=Path(f"/{identifier}.md"),
        keywords=(),
        extra={"score": score},
        content_text="",
        display_blocks={},
        display_label=identifier,
        display_alias="",
    )


@dataclass
class _Graph:
    entities: dict[str, EntityRecord] = field(default_factory=dict)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.entities.get(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return None

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return []


_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"component"}),
    known_connection_types=frozenset(),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={"score": "integer"},
    connection_attribute_types={},
)


def _input(graph: _Graph) -> BindingEvaluationInput:
    return BindingEvaluationInput(tuple(graph.entities), (), graph, _REGISTRIES)


def _criteria(score: int) -> EntityCriteriaGroup:
    return EntityCriteriaGroup(children=(AttributeCondition("score", "gte", ValueRef(literal=score)),))


def test_bindings_evaluate_in_declaration_order_and_materialize_stably() -> None:
    graph = _Graph({"E2": _entity("E2", score=2), "E1": _entity("E1", score=3)})
    bindings = (
        QueryBinding("eligible", EntitySetType(frozenset({"component"})), select="entities", criteria=_criteria(2)),
        QueryBinding("scores", ScalarType("integer"), tuple_of=("eligible",)),
    )
    result = evaluate_bindings(bindings, parameters={}, input=_input(graph))
    eligible = result.environment.bindings["eligible"]
    assert isinstance(eligible, tuple)
    assert tuple(item.artifact_id for item in eligible) == ("E1", "E2")
    assert result.environment.bindings["scores"] == (eligible,)


@pytest.mark.parametrize(
    ("result_type", "scores", "raises"),
    (
        (EntityInstanceType(frozenset({"component"})), (), True),
        (EntityInstanceType(frozenset({"component"})), (1,), False),
        (EntityInstanceType(frozenset({"component"})), (1, 2), True),
        (OptionalType(EntityInstanceType(frozenset({"component"}))), (), False),
        (OptionalType(EntityInstanceType(frozenset({"component"}))), (1, 2), True),
    ),
)
def test_instance_bindings_assert_declared_cardinality(
    result_type: object, scores: tuple[int, ...], raises: bool
) -> None:
    graph = _Graph({f"E{score}": _entity(f"E{score}", score=score) for score in scores})
    binding = QueryBinding("single", result_type, select="entities", criteria=EntityCriteriaGroup())
    if raises:
        with pytest.raises(BindingCardinalityError):
            evaluate_bindings((binding,), parameters={}, input=_input(graph))
    else:
        result = evaluate_bindings((binding,), parameters={}, input=_input(graph))
        assert "single" in result.environment.bindings


def test_binding_projection_and_quantifiers_follow_empty_value_rules() -> None:
    graph = _Graph({"E1": _entity("E1", score=3)})
    binding = QueryBinding(
        "scores", EntitySetType(frozenset({"component"})), select="entities", criteria=_criteria(9), project="score"
    )
    environment = evaluate_bindings((binding,), parameters={}, input=_input(graph)).environment
    any_condition = AttributeCondition("score", "lt", ValueRef(kind="binding", binding="scores", quantifier="any"))
    all_condition = AttributeCondition("score", "lt", ValueRef(kind="binding", binding="scores", quantifier="all"))
    entity = graph.entities["E1"]
    assert not evaluate_entity_criteria(
        EntityCriteriaGroup(children=(any_condition,)),
        entity,
        read_access=graph,
        registries=_REGISTRIES,
        environment=environment,
    ).matched
    assert evaluate_entity_criteria(
        EntityCriteriaGroup(children=(all_condition,)),
        entity,
        read_access=graph,
        registries=_REGISTRIES,
        environment=environment,
    ).matched
