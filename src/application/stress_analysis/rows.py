"""An analysis document's table rows as plain values, and which set a stressor row belongs to."""
from __future__ import annotations

from typing import Any

from src.application.artifacts.document_table_rows import DocumentTables
from src.domain.repository.repo_default_stress_analysis import TEST_SET

Row = dict[str, Any]


def rows_of(tables: DocumentTables, name: str) -> list[Row]:
    """Each row of table *name* as its id and its cells' values, in the document's order."""
    table = tables.table(name)
    return [
        {"id": row.row_id, **{key: cell.value for key, cell in row.cells.items()}}
        for row in table.rows
    ] if table else []


def in_test_set(row: Row) -> bool:
    """Whether a stressor row is held apart in the test set. A row naming no set is a design stressor."""
    return row.get("set") == TEST_SET


def held_apart(tables: DocumentTables) -> frozenset[str]:
    """The ids of the stressors held in the test set."""
    return frozenset(row["id"] for row in rows_of(tables, "stressors") if in_test_set(row))
