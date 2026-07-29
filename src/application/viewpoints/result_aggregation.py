"""Budget-triggered aggregation for one execution: decides whether the COMPLETE
population exceeds the effective legibility budget on a graph surface and, if so,
aggregates it along the resolved dimension. Pure application glue over
``src.domain.viewpoints.viewpoint_aggregation``."""

from __future__ import annotations

from src.application.viewpoints.ports import RepositoryReadAccess
from src.domain.viewpoints.viewpoint_aggregation import (
    AggregateConnection,
    AggregateMember,
    AggregationSummary,
    aggregate_population,
    resolve_aggregation_dimension,
)
from src.domain.viewpoints.viewpoints import PresentationSpec


def aggregation_for_result(
    presentation: PresentationSpec | None,
    *,
    total_entity_count: int,
    population_entity_ids: tuple[str, ...],
    aggregate_connections: tuple[AggregateConnection, ...],
    read_access: RepositoryReadAccess,
    default_legibility_budget: int,
) -> AggregationSummary | None:
    """The result's ``aggregation`` block, or ``None`` when the population fits the
    budget or the representation is not a graph surface. Always fed the COMPLETE
    (pre-limit) population — a truncated-then-aggregated result is not an overview."""
    legibility_budget = (
        presentation.legibility_budget
        if presentation is not None and presentation.legibility_budget is not None
        else default_legibility_budget
    )
    representation = presentation.representation if presentation is not None else "exploration"
    if representation not in ("exploration", "diagram") or total_entity_count <= legibility_budget:
        return None
    members = tuple(
        AggregateMember(
            entity_id=record.artifact_id,
            entity_type=record.artifact_type,
            group=record.group,
            domain=record.domain,
        )
        for entity_id in population_entity_ids
        if (record := read_access.get_entity(entity_id)) is not None
    )
    return aggregate_population(
        members,
        aggregate_connections,
        dimension=resolve_aggregation_dimension(
            presentation.aggregate_by if presentation is not None else None,
            presentation.group_by if presentation is not None else None,
        ),
        legibility_budget=legibility_budget,
    )
