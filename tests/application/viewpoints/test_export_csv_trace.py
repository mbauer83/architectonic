"""CSV projection of a trace execution: role-specific `trace:` columns, `param:`
provenance with canonical values, and trace-table row ordering."""

from __future__ import annotations

import csv
import io

from src.application.viewpoints.execution_result import EntityItemSummary, ViewpointExecutionResult
from src.application.viewpoints.export_csv import build_execution_csv
from src.application.viewpoints.trace_pipeline import TraceRow, TraceTable
from src.domain.viewpoints.viewpoint_trace_result import (
    AuthoritativePatternResult,
    Coverage,
    DiagnosticPatternResult,
    TerminalObligation,
)


def _entity(entity_id: str, name: str) -> EntityItemSummary:
    return EntityItemSummary(
        id=entity_id, name=name, type="goal", specialization_slugs=(), domain="motivation",
        group="motivation", membership="primary", status="active", version="0.1.0",
    )


def _authoritative(verdict: str, status: str) -> AuthoritativePatternResult:
    return AuthoritativePatternResult(
        verdict=verdict,  # type: ignore[arg-type]
        status_code=status,  # type: ignore[arg-type]
        coverage=Coverage(2, 3),
        incomplete_branch_count=0,
        failing_obligations=(TerminalObligation("GOL@1", "REQ@9"),),
        failing_overflow=0,
        last_satisfied_ids=("REQ@1", "REQ@2"),
        missing_expected=("requirement",),
        shortcut=False,
    )


def _result(rows: tuple[TraceRow, ...], entities: tuple[EntityItemSummary, ...]) -> ViewpointExecutionResult:
    return ViewpointExecutionResult(
        slug="motivation-coverage", version=1, query_schema=1, repo_scope="both",
        executed_at="2026-07-20T00:00:00Z", index_generation=1,
        entity_ids=tuple(e.id for e in entities), connection_ids=(), entities=entities, connections=(),
        total_entity_count=len(entities), returned_entity_count=len(entities),
        total_connection_count=0, returned_connection_count=0, truncated=False, entity_limit=50,
        matrix_axes=None, warnings=(), duration_ms=1.0, query_summary="",
        bound_parameters={"scope": ("goal", "outcome"), "gaps_only": True},
        trace_table=TraceTable(rows=rows, total_rows=len(rows), returned_rows=len(rows),
                               truncated=False, derived_truncated=False),
    )


def _rows_of(csv_text: str) -> list[list[str]]:
    body = [line for line in csv_text.splitlines() if not line.startswith("#")]
    return list(csv.reader(io.StringIO("\n".join(body))))


def _trace_row(entity_id: str, name: str, verdict: str, status: str) -> TraceRow:
    return TraceRow(
        entity_id=entity_id, entity_type="goal", name=name, tier="engagement", verdict=verdict,  # type: ignore[arg-type]
        pattern_results=(
            ("motivation", _authoritative(verdict, status)),
            ("business_coverage", DiagnosticPatternResult(observation="none_observed", last_satisfied_ids=())),
        ),
    )


class TestTraceColumns:
    def test_role_specific_headers(self) -> None:
        result = _result((_trace_row("GOL@1", "A", "gap", "shortcut"),), (_entity("GOL@1", "A"),))
        header = _rows_of(build_execution_csv(result, None, None))[0]
        assert "trace:motivation:verdict" in header
        assert "trace:motivation:coverage" in header
        # A diagnostic pattern gets an OBSERVATION column and never a verdict one, so absence
        # cannot be misread as an authoritative pass or gap.
        assert "trace:business_coverage:observation" in header
        assert "trace:business_coverage:verdict" not in header

    def test_cell_values(self) -> None:
        result = _result((_trace_row("GOL@1", "A", "gap", "shortcut"),), (_entity("GOL@1", "A"),))
        rows = _rows_of(build_execution_csv(result, None, None))
        header, row = rows[0], rows[1]
        cells = dict(zip(header, row, strict=True))
        assert cells["trace:motivation:verdict"] == "gap"
        assert cells["trace:motivation:status"] == "shortcut"
        assert cells["trace:motivation:coverage"] == "2/3"
        assert cells["trace:motivation:missing"] == "requirement"
        assert cells["trace:motivation:witness_ids"] == "REQ@1|REQ@2"
        assert cells["trace:business_coverage:observation"] == "none_observed"


class TestParameterProvenance:
    def test_canonical_values_never_a_python_repr(self) -> None:
        result = _result((_trace_row("GOL@1", "A", "gap", "shortcut"),), (_entity("GOL@1", "A"),))
        rows = _rows_of(build_execution_csv(result, None, None))
        cells = dict(zip(rows[0], rows[1], strict=True))
        assert cells["param:scope"] == "goal|outcome"
        assert cells["param:gaps_only"] == "True"
        assert "(" not in cells["param:scope"]  # not a tuple repr


class TestRowOrdering:
    def test_export_follows_trace_table_order_not_entity_order(self) -> None:
        # Entities are id-sorted; the trace table puts the gap first. The export is the
        # coverage table, so it must follow the verdict ordering.
        entities = (_entity("GOL@1", "Alpha"), _entity("GOL@2", "Beta"))
        rows = (_trace_row("GOL@2", "Beta", "gap", "shortcut"), _trace_row("GOL@1", "Alpha", "pass", "ok"))
        exported = _rows_of(build_execution_csv(_result(rows, entities), None, None))
        assert [row[0] for row in exported[1:]] == ["GOL@2", "GOL@1"]
