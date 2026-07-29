"""CSV export: complete rows, provenance block, authored columns from server-resolved
values with honest empties."""

from __future__ import annotations

import csv
import io

from src.application.viewpoints.execution_result import EntityItemSummary, ViewpointExecutionResult
from src.application.viewpoints.export_csv import build_execution_csv
from src.domain.viewpoints.viewpoints import ColumnSpec


def _entity(identifier: str, **kw: object) -> EntityItemSummary:
    defaults: dict[str, object] = dict(
        id=identifier, name=f"Name {identifier}", type="requirement", specialization_slugs=(),
        domain="motivation", group="motivation-narrative", membership="primary", status="draft",
        version="0.1.0",
    )
    defaults.update(kw)
    return EntityItemSummary(**defaults)  # type: ignore[arg-type]


def _result(entities: tuple[EntityItemSummary, ...]) -> ViewpointExecutionResult:
    return ViewpointExecutionResult(
        slug="requirements-coverage-gaps", version=1, query_schema=1, repo_scope="both",
        executed_at="2026-07-18T02:00:00Z", index_generation=85,
        entity_ids=tuple(e.id for e in entities), connection_ids=(), entities=entities, connections=(),
        total_entity_count=len(entities), returned_entity_count=len(entities),
        total_connection_count=0, returned_connection_count=0, truncated=False, entity_limit=500,
        matrix_axes=None, warnings=(), duration_ms=1.0, query_summary="test",
    )


def test_export_carries_provenance_and_every_row() -> None:
    entities = tuple(_entity(f"REQ@{i}") for i in range(242))
    text = build_execution_csv(_result(entities), None, {"anchor": "X@1"})

    provenance = [line for line in text.splitlines() if line.startswith("# ")]
    assert "# viewpoint: requirements-coverage-gaps v1" in provenance
    assert "# parameters: anchor=X@1" in provenance
    assert "# executed_at: 2026-07-18T02:00:00Z" in provenance
    assert "# index_generation: 85" in provenance
    assert any("242/242" in line for line in provenance)

    rows = list(csv.reader(io.StringIO("\n".join(line for line in text.splitlines() if not line.startswith("# ")))))
    assert rows[0] == ["id", "name", "type", "specialization", "group", "status", "version"]
    assert len(rows) - 1 == 242  # COMPLETE — every row, not a visible page


def test_authored_columns_use_server_resolved_values_with_honest_empties() -> None:
    entities = (
        _entity("REQ@1", column_values={"criticality": "high"}),
        _entity("REQ@2", column_values={"criticality": None}),
    )
    columns = (ColumnSpec(label="Criticality", source="criticality"), ColumnSpec(label="Status", source="status"))
    text = build_execution_csv(_result(entities), columns, None)

    rows = list(csv.reader(io.StringIO("\n".join(line for line in text.splitlines() if not line.startswith("# ")))))
    # The fixed 'status' column already covers the authored Status column source.
    assert rows[0][-1] == "Criticality"
    assert rows[1][-1] == "high"
    assert rows[2][-1] == ""  # missing value exported empty, never guessed
