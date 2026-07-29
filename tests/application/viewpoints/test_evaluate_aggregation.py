"""Scale-adaptive aggregation through the execution use case: the budget trigger, the
aggregate-before-limit ordering rule, and the flat/aggregate count invariant."""

from __future__ import annotations

from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionRequest, evaluate_viewpoint
from src.domain.viewpoints.viewpoint_criteria import EntityCriteriaGroup
from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    PresentationSpec,
    ViewpointCatalog,
    ViewpointDefinition,
)
from tests.application.viewpoints._fixtures import REGISTRIES, Store, connection, entity

_DEFAULTS: dict[str, object] = dict(max_entities=500, default_limit=500, timeout_seconds=10.0, index_generation=None)


def _store(count: int) -> Store:
    entities = {
        f"ENT@{i:03d}": entity(artifact_id=f"ENT@{i:03d}", name=f"Entity {i}", group=f"group-{i % 3}")
        for i in range(count)
    }
    connections = [
        connection(artifact_id=f"CON@{i:03d}", source=f"ENT@{i:03d}", target=f"ENT@{(i + 1) % count:03d}")
        for i in range(count)
    ]
    return Store(entities=entities, connections=connections)


def _catalog(*, legibility_budget: int | None = None, aggregate_by: str | None = None) -> ViewpointCatalog:
    definition = ViewpointDefinition(
        slug="dense-view",
        version=1,
        name="Dense",
        query=ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup()),
        presentation=PresentationSpec(
            representation="exploration", legibility_budget=legibility_budget, aggregate_by=aggregate_by
        ),
    )
    return ViewpointCatalog(entries=(definition,))


def _run(store: Store, catalog: ViewpointCatalog, **overrides: object):
    kwargs = {**_DEFAULTS, **overrides}
    return evaluate_viewpoint(
        ViewpointExecutionRequest(slug="dense-view"),
        catalog=catalog,
        read_access=store,
        registries=REGISTRIES,
        **kwargs,
    )


class TestBudgetTrigger:
    def test_under_budget_result_carries_no_aggregation(self) -> None:
        result = _run(_store(10), _catalog(legibility_budget=100))
        assert result.aggregation is None

    def test_over_budget_result_aggregates_along_the_declared_dimension(self) -> None:
        result = _run(_store(30), _catalog(legibility_budget=20, aggregate_by="group"))
        assert result.aggregation is not None
        assert result.aggregation.dimension == "group"
        assert result.aggregation.legibility_budget == 20
        assert {node.dimension_value for node in result.aggregation.nodes} == {"group-0", "group-1", "group-2"}

    def test_flat_and_aggregate_counts_agree(self) -> None:
        result = _run(_store(30), _catalog(legibility_budget=20))
        assert result.aggregation is not None
        assert sum(node.member_count for node in result.aggregation.nodes) == result.total_entity_count


class TestAggregateBeforeLimit:
    def test_a_truncated_execution_still_aggregates_the_complete_population(self) -> None:
        store = _store(30)
        catalog = _catalog(legibility_budget=20)
        result = evaluate_viewpoint(
            ViewpointExecutionRequest(slug="dense-view", limit=10),
            catalog=catalog,
            read_access=store,
            registries=REGISTRIES,
            max_entities=500,
            default_limit=500,
            timeout_seconds=10.0,
            index_generation=None,
        )
        assert result.returned_entity_count == 10
        assert result.truncated is True
        assert result.aggregation is not None
        assert sum(node.member_count for node in result.aggregation.nodes) == 30
        assert sum(edge.member_count for edge in result.aggregation.edges) == 30
