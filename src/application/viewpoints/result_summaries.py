"""Result-assembly helpers for ``EvaluateViewpoint``: matrix axis membership and the
ordered witness chain a connection summary carries."""

from __future__ import annotations

from src.application.viewpoints.execution_result import MatrixAxisIds
from src.application.viewpoints.ports import RepositoryReadAccess
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria_evaluation import evaluate_entity_criteria
from src.domain.viewpoints.viewpoint_projection import ProjectedOccurrence
from src.domain.viewpoints.viewpoint_witness_steps import WitnessStep, order_witness_steps
from src.domain.viewpoints.viewpoints import PresentationSpec


def matrix_axis_ids(
    presentation: PresentationSpec | None,
    retained_entities: list[EntityRecord],
    *,
    read_access: RepositoryReadAccess,
    registries: RegistrySnapshot,
) -> tuple[MatrixAxisIds | None, frozenset[str]]:
    if presentation is None or presentation.representation != "matrix":
        return None, frozenset()
    if presentation.row_criteria is None or presentation.column_criteria is None:
        return None, frozenset()
    drift: set[str] = set()
    rows: list[str] = []
    columns: list[str] = []
    for record in retained_entities:
        row_outcome = evaluate_entity_criteria(
            presentation.row_criteria, record, read_access=read_access, registries=registries
        )
        drift |= row_outcome.schema_drift
        if row_outcome.matched:
            rows.append(record.artifact_id)
        column_outcome = evaluate_entity_criteria(
            presentation.column_criteria, record, read_access=read_access, registries=registries
        )
        drift |= column_outcome.schema_drift
        if column_outcome.matched:
            columns.append(record.artifact_id)
    return MatrixAxisIds(row_entity_ids=tuple(sorted(rows)), column_entity_ids=tuple(sorted(columns))), frozenset(drift)


def ordered_witness_steps_for(
    item: ProjectedOccurrence, source: str, target: str, read_access: RepositoryReadAccess
) -> tuple[WitnessStep, ...]:
    if not item.via_connection_ids:
        return ()
    records = tuple(
        record
        for connection_id in item.via_connection_ids
        if (record := read_access.get_connection(connection_id)) is not None
    )
    if len(records) != len(item.via_connection_ids):
        return ()  # a witness was deleted since derivation — the chain is unavailable
    return order_witness_steps(source, target, records)
