"""CSV export of a viewpoint execution result.

The export is COMPLETE — the full result at the execution's generation, never the visible
page of a paginated view (a 242-row result exported from one page would silently look
complete). Provenance travels in comment lines at the top (slug/version, parameters,
executed_at, index generation, counts), so an exported file is citable evidence, not a
bare grid.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping

from src.application.viewpoints.execution_result import EntityItemSummary, ViewpointExecutionResult
from src.domain.viewpoints.viewpoint_trace_result import AuthoritativePatternResult, PatternResult
from src.domain.viewpoints.viewpoints import ColumnSpec

_FIXED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("id", "id"),
    ("name", "name"),
    ("type", "type"),
    ("specialization", "specialization"),
    ("group", "group"),
    ("status", "status"),
    ("version", "version"),
)


def build_execution_csv(
    result: ViewpointExecutionResult,
    columns: tuple[ColumnSpec, ...] | None,
    parameters: Mapping[str, object] | None,
) -> str:
    """Provenance block + header + one row per result entity. Authored columns render
    their server-resolved ``column_values`` (missing values stay empty, never guessed)."""
    buffer = io.StringIO()
    identity = f"{result.slug} v{result.version}" if result.slug else "(ad-hoc query)"
    parameter_text = (
        ", ".join(f"{name}={value}" for name, value in sorted(parameters.items())) if parameters else "(none)"
    )
    for line in (
        f"viewpoint: {identity}",
        f"parameters: {parameter_text}",
        f"executed_at: {result.executed_at}",
        f"index_generation: {result.index_generation}",
        f"entities: {result.returned_entity_count}/{result.total_entity_count} · "
        f"connections: {result.returned_connection_count}/{result.total_connection_count}",
    ):
        buffer.write(f"# {line}\r\n")

    authored = [column for column in (columns or ()) if column.source not in {name for name, _ in _FIXED_COLUMNS}]
    trace_headers, trace_cells_by_id = _trace_projection(result)
    provenance_headers, provenance_cells = _parameter_provenance(result)
    writer = csv.writer(buffer)
    writer.writerow(
        [label for label, _ in _FIXED_COLUMNS]
        + [column.label or column.source for column in authored]
        + trace_headers
        + provenance_headers
    )
    for entity in _export_order(result):
        fixed = [
            entity.id,
            entity.name,
            entity.type,
            ", ".join(entity.specialization_slugs),
            entity.group,
            entity.status,
            entity.version,
        ]
        values = entity.column_values or {}
        extra = ["" if (value := values.get(column.source)) is None else str(value) for column in authored]
        trace = trace_cells_by_id.get(entity.id, [""] * len(trace_headers))
        writer.writerow(fixed + extra + trace + provenance_cells)
    return buffer.getvalue()


def _export_order(result: ViewpointExecutionResult) -> list[EntityItemSummary]:
    """A trace execution's authoritative row order is the trace table's (worst verdict first),
    not the id-sorted entity order — the coverage table IS the result. Rows the entity limit
    dropped are skipped rather than emitted with empty identity columns."""
    if result.trace_table is None:
        return list(result.entities)
    by_id = {entity.id: entity for entity in result.entities}
    ordered = [by_id[row.entity_id] for row in result.trace_table.rows if row.entity_id in by_id]
    return ordered or list(result.entities)


def _pattern_columns(outcome: PatternResult) -> tuple[tuple[str, str], ...]:
    """The reported column set for ONE pattern result, as ordered ``(suffix, cell)`` pairs.

    Header and cell come from this single source, so they cannot drift apart — a field added
    here appears in both or in neither. The pattern NAMES that prefix these suffixes are
    dynamic (whatever the declaration authored); the suffixes are the DTO's own shape, and the
    curated subset is deliberate — this is a report, not a dump of every field.

    Roles project differently on purpose — a diagnostic pattern has no verdict column at all,
    so a verdict-neutral absence can never land in a column a reader would read as a gap.
    """
    if isinstance(outcome, AuthoritativePatternResult):
        return (
            ("verdict", outcome.verdict),
            ("status", outcome.status_code),
            ("coverage", f"{outcome.coverage.covered}/{outcome.coverage.applicable}"),
            ("missing", "|".join(outcome.missing_expected)),
            ("witness_ids", "|".join(outcome.last_satisfied_ids)),
        )
    return (
        ("observation", outcome.observation),
        ("status", outcome.status_code),
        ("witness_ids", "|".join(outcome.last_satisfied_ids)),
    )


def _trace_projection(result: ViewpointExecutionResult) -> tuple[list[str], dict[str, list[str]]]:
    """Headers and per-row cells for the declared trace patterns. Every row carries the same
    patterns in declaration order, so the first row establishes the header layout."""
    table = result.trace_table
    if table is None or not table.rows:
        return [], {}
    headers = [
        f"trace:{name}:{suffix}"
        for name, outcome in table.rows[0].pattern_results
        for suffix, _cell in _pattern_columns(outcome)
    ]
    cells_by_id = {
        row.entity_id: [cell for _name, outcome in row.pattern_results for _suffix, cell in _pattern_columns(outcome)]
        for row in table.rows
    }
    return headers, cells_by_id


def _parameter_provenance(result: ViewpointExecutionResult) -> tuple[list[str], list[str]]:
    """One ``param:<name>`` column per bound parameter, carrying the CANONICAL serialized
    value — a set joins its members with ``|`` rather than leaking a Python repr, so the file
    records exactly what a shared URL would reproduce."""
    headers: list[str] = []
    cells: list[str] = []
    for name, value in sorted(result.bound_parameters.items()):
        headers.append(f"param:{name}")
        cells.append("|".join(str(member) for member in value) if isinstance(value, (list, tuple)) else str(value))
    return headers, cells
