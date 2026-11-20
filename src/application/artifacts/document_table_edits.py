"""Rows of a document's typed table added, changed and removed where they stand.

**A row is addressed by its id** — the first cell, `S3` — which is what a row keeps when the table is
reordered and what other rows, documents and analyses name it by. A row that carries none cannot be
addressed, and the edit says so.

**A change states the row it was based on.** `based_on` is the row as the caller read it: each
stated cell's value by column name. When the row no longer holds that, another writer changed it
first, and the edit is refused with the row and both values named — never merged, never applied over
the other writer's change. Edits of different rows do not meet: each is compared with its own row,
so two writers changing two rows both succeed, in either order. Adding a row is compared with
nothing and takes the next id as the table then stands.

**What a cell's value is** is the reading's: a value column's typed value, a reference column's
artifact id, a row column's row id, a list of them for a `many` column — and, for a stated cell the
reading could make no value of, the cell's text as spelled, so that no cell is invisible to the
comparison. A cell is written from the same vocabulary: a typed value through the typed-property
codec, a row id through the declaration, and a reference as an artifact id or a markdown link, which
`link_of` makes into the link the document stores.

Every line of the document that is not a changed, removed or added row stays as it was. That is the
table owner's `with_rows`; nothing here spells a row.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from src.application.artifacts.document_part_edits import (
    CellValue,
    DocumentEditRefused,
    RowAddition,
    RowChange,
    RowChangedSinceRead,
    RowEdit,
    RowRemoval,
    TableRowEdits,
)
from src.application.artifacts.document_schema import DocumentSchema
from src.application.artifacts.document_sections import document_body
from src.application.artifacts.document_table_rows import TypedCell, TypedRow, TypedTable, read_document_tables
from src.application.artifacts.document_tables import ColumnSpec, format_row_ids
from src.domain.artifact_id import canonical_entity_key
from src.domain.markdown_table import MarkdownTable, escape_cell, with_rows
from src.domain.ontology_representation.property_value import encode

#: A reference as the caller states it — an artifact id or a markdown link — to the link stored.
LinkOf = Callable[[str], str]

_LINK_SEPARATOR = ", "


@dataclass(frozen=True)
class RowsEdited:
    """The document with the edits made, and the ids the added rows were given, in the order added."""

    content: str
    added_row_ids: tuple[str, ...] = ()


@dataclass
class _Pending:
    """The edits of one call, gathered against the table as it was read."""

    changed: dict[int, tuple[str, ...]] = field(default_factory=dict)
    removed: set[int] = field(default_factory=set)
    added: list[tuple[str, ...]] = field(default_factory=list)
    added_ids: list[str] = field(default_factory=list)


def held_value(cell: TypedCell) -> CellValue:
    """What a cell holds, as an edit's `based_on` states it: its value, or its text where it has none."""
    return cell.value if cell.value is not None else (cell.spelled or None)


def row_values(row: TypedRow) -> dict[str, CellValue]:
    """A row as an edit is based on it: every stated cell's value, by column name."""
    return {name: value for name, cell in row.cells.items() if (value := held_value(cell)) is not None}


def _items(value: CellValue) -> list[str | int | float | bool]:
    return [] if value is None or value == "" else value if isinstance(value, list) else [value]


def _comparable(column: ColumnSpec, value: CellValue) -> tuple[str, ...]:
    """A cell's value in the one form two statements of it are compared in."""
    items = _items(value)
    if not items:
        return ()
    if column.kind == "value":
        return (encode(value),) if value is not None else ()
    return tuple(canonical_entity_key(str(item)) for item in items)


def _shown(value: CellValue) -> str:
    return "nothing" if not _items(value) else json.dumps(value, ensure_ascii=False)


def _spelled(table: TypedTable, column: ColumnSpec, value: CellValue, link_of: LinkOf) -> str:
    """The cell that states `value` in `column`, as the table owner writes one."""
    items = _items(value)
    if not items:
        return ""
    too_many = len(items) > 1 and not column.many
    if column.kind != "value" and (too_many or not all(isinstance(item, str) for item in items)):
        takes = "one row id" if column.kind == "row" else "one artifact id or markdown link"
        raise DocumentEditRefused(
            f"Table '{table.spec.name}' column '{column.name}' takes {takes}"
            f"{', or a list of them' if column.many else ''}, and was given {_shown(value)}."
        )
    match column.kind:
        case "row":
            return escape_cell(format_row_ids(str(item) for item in items))
        case "reference":
            return escape_cell(_LINK_SEPARATOR.join(link_of(str(item)) for item in items))
        case _:
            return _encoded(table, column, value)


def _encoded(table: TypedTable, column: ColumnSpec, value: CellValue) -> str:
    try:
        return encode(value) if value is not None else ""
    except TypeError:
        raise DocumentEditRefused(
            f"Table '{table.spec.name}' column '{column.name}' takes a text, a number, true or false, or a "
            f"list of them, and was given {json.dumps(value, ensure_ascii=False, default=str)}."
        ) from None


def _column(table: TypedTable, name: str) -> ColumnSpec:
    declared = next((column for column in table.spec.columns if column.name == name), None)
    if declared is None:
        raise DocumentEditRefused(
            f"Table '{table.spec.name}' declares no column '{name}'. "
            f"Its columns are: {', '.join(column.name for column in table.spec.columns)}."
        )
    if name not in table.positions:
        raise DocumentEditRefused(
            f"Table '{table.spec.name}' has no column headed '{declared.title}' in this document, so a value "
            f"for '{name}' has nowhere to be written. Add the column to the table's header first."
        )
    return declared


def _with_cells(
    table: TypedTable, cells: Sequence[str], stated: Mapping[str, CellValue], link_of: LinkOf
) -> tuple[str, ...]:
    """`cells` of one row with each stated column's cell rewritten."""
    columns = {name: _column(table, name) for name in stated}
    rewritten = {
        table.positions[name]: _spelled(table, columns[name], value, link_of) for name, value in stated.items()
    }
    return tuple(rewritten.get(at, cell) for at, cell in enumerate(cells))


def _row_index(table: TypedTable, row_id: str) -> int:
    carried = [index for index, row in enumerate(table.rows) if row.row_id == row_id]
    if len(carried) == 1:
        return carried[0]
    if carried:
        raise DocumentEditRefused(
            f"Table '{table.spec.name}': {len(carried)} rows carry the id '{row_id}', so it addresses none of "
            "them. Give each row its own id in the document first."
        )
    held = [row.row_id for row in table.rows if row.row_id]
    raise DocumentEditRefused(
        f"Table '{table.spec.name}' holds no row '{row_id}'. "
        + (f"It holds: {', '.join(held)}." if held else "It holds no row with an id.")
    )


def _assert_based_on_what_stands(table: TypedTable, row: TypedRow, based_on: Mapping[str, CellValue]) -> None:
    stands = row_values(row)
    differing = [
        f"'{column.name}' was {_shown(based_on.get(column.name))} and is now {_shown(stands.get(column.name))}"
        for column in table.spec.columns
        if _comparable(column, based_on.get(column.name)) != _comparable(column, stands.get(column.name))
    ]
    if differing:
        raise RowChangedSinceRead(
            f"Table '{table.spec.name}' row {row.row_id} has changed since it was read: {'; '.join(differing)}. "
            "Read the row again and make the edit on what it holds now."
        )


def _gather(table: TypedTable, held: MarkdownTable, edits: Sequence[RowEdit], link_of: LinkOf) -> _Pending:
    addressed = Counter(edit.row_id for edit in edits if not isinstance(edit, RowAddition))
    if repeated := sorted(row_id for row_id, count in addressed.items() if count > 1):
        raise DocumentEditRefused(
            f"Table '{table.spec.name}': row {', '.join(repeated)} is edited more than once in one call. "
            "State each row's change once."
        )
    numbers = [number for row in table.rows if (number := table.spec.row_number(row.row_id)) is not None]
    pending = _Pending()
    for edit in edits:
        match edit:
            case RowAddition(cells=cells):
                row_id = table.spec.row_id(max(numbers, default=0) + len(pending.added) + 1)
                empty = (escape_cell(row_id), *("" for _ in held.header[1:]))
                pending.added.append(_with_cells(table, empty, cells, link_of))
                pending.added_ids.append(row_id)
            case RowChange(row_id=row_id, based_on=based_on, cells=cells):
                index = _row_index(table, row_id)
                _assert_based_on_what_stands(table, table.rows[index], based_on)
                pending.changed[index] = _with_cells(table, held.rows[index], cells, link_of)
            case RowRemoval(row_id=row_id, based_on=based_on):
                index = _row_index(table, row_id)
                _assert_based_on_what_stands(table, table.rows[index], based_on)
                pending.removed.add(index)
    return pending


def edit_table_rows(
    content: str, edits: TableRowEdits, *, schema: DocumentSchema, doc_path: Path, link_of: LinkOf
) -> RowsEdited:
    """`content` with `edits` made to one declared table, and every other line as it was.

    Raises `DocumentEditRefused` naming what to change, and `RowChangedSinceRead` for a row that is
    no longer what its edit was based on.
    """
    if not edits.edits:
        raise DocumentEditRefused(f"The edit of table '{edits.table}' names no row to add, change or remove.")
    table = read_document_tables(doc_path, content, schema).table(edits.table)
    if table is None:
        declared = [spec.name for section in schema.sections for spec in section.tables]
        raise DocumentEditRefused(
            f"Document type '{schema.doc_type}' declares no table '{edits.table}'. "
            + (f"It declares: {', '.join(declared)}." if declared else "It declares no table.")
        )
    held = table.held
    if held is None:
        raise DocumentEditRefused(
            f"Section '{table.section}' holds no table '{table.spec.name}'. Add one headed "
            f"{' | '.join(table.spec.header)}, and then its rows."
        )
    pending = _gather(table, held, edits.edits, link_of)
    body = document_body(content)
    edited = with_rows(body, held, changed=pending.changed, removed=pending.removed, added=pending.added)
    return RowsEdited(content[: len(content) - len(body)] + edited, tuple(pending.added_ids))
