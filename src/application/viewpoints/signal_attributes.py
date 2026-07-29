"""Signal-derived attribute orchestration for viewpoint evaluation.

Partitioned out of the pure graph evaluation path: attributes with
``source: security-signal`` are batch-fetched from the injected capability
(one call per phase — criteria-referenced attributes over the full scoped
candidate set, presentation-only ones over the retained population) and merged
into the evaluation environment under the same ``(entity_id, name)`` keys the
graph evaluator uses. An unavailable batch merges nothing and yields one
explicit warning — values from different snapshots are never mixed.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.viewpoints.ports import SignalAttributeCapability
from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute
from src.domain.viewpoints.viewpoint_evaluation_context import EvaluationEnvironment


def fetch_and_merge_signal_attributes(
    capability: SignalAttributeCapability | None,
    attributes: tuple[DerivedAttribute, ...],
    entity_ids: Sequence[str],
    environment: EvaluationEnvironment,
) -> tuple[EvaluationEnvironment, str | None]:
    """Returns the (possibly extended) environment and a warning when the batch
    was unavailable (None capability counts as unavailable-by-configuration)."""
    if not attributes or not entity_ids:
        return environment, None
    if capability is None:
        return environment, "signals unavailable: no signal capability configured"
    metric_names = tuple(dict.fromkeys(
        attribute.metric for attribute in attributes if attribute.metric
    ))
    batch = capability.fetch_metrics(tuple(entity_ids), metric_names)
    if not batch.available:
        return environment, f"signals unavailable: {batch.note or 'no coherent snapshot'}"
    values = dict(environment.derived_values)
    names_by_metric = {
        attribute.metric: attribute.name for attribute in attributes if attribute.metric
    }
    for (entity_id, metric_name), value in batch.values.items():
        name = names_by_metric.get(metric_name)
        if name is not None and value is not None:
            values[(entity_id, name)] = value
    return (
        EvaluationEnvironment(
            bindings=environment.bindings,
            parameters=environment.parameters,
            derived_values=values,
        ),
        None,
    )
