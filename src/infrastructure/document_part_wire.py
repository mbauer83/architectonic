"""The wire form of an edit of one part of a document, and of a typed table's rows as they are read.

One spelling for both surfaces that carry it: the REST request bodies are these models, and the MCP
tools take the same models as their arguments, so the two cannot come to accept different rows. What
each edit means is said in `src.application.artifacts.document_part_edits`; nothing here decides
anything but which edit a request states.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from src.application.artifacts.document_part_edits import (
    PartEdit,
    RowAddition,
    RowChange,
    RowEdit,
    RowRemoval,
    SectionReplacement,
    TableRowEdits,
    TextReplacement,
)
from src.application.artifacts.document_table_edits import row_values
from src.application.artifacts.document_table_rows import DocumentTables

_Scalar = StrictStr | StrictBool | StrictInt | StrictFloat

#: A cell's value: its column's typed value, an artifact id or row id for a column that addresses
#: one, a list for a column that takes several, and null for an empty cell.
CellValueBody = _Scalar | list[_Scalar] | None


class SectionEditBody(BaseModel):
    """Replace what stands under one heading; the rest of the document is left byte for byte."""

    #: The titles from the `##` section down to the heading: `["Decision"]`, `["Decision", "Rationale"]`.
    heading_path: list[str] = Field(min_length=1)
    #: The text under the heading, without the heading line itself.
    text: str


class TextReplacementBody(BaseModel):
    """Replace an exact text of the body, refused unless it occurs as often as expected."""

    find: str = Field(min_length=1)
    replacement: str
    expected_matches: int = Field(default=1, ge=1)


class AddRowBody(BaseModel):
    op: Literal["add"]
    #: Values by column name. The row's id is allocated and answered in `added_row_ids`.
    cells: dict[str, CellValueBody] = Field(default_factory=dict)


class ChangeRowBody(BaseModel):
    op: Literal["change"]
    row_id: str
    #: The row as it was read — its `values` — which the change is refused against when it has moved.
    based_on: dict[str, CellValueBody]
    #: The cells to change, by column name. A column not named keeps its cell.
    cells: dict[str, CellValueBody]


class RemoveRowBody(BaseModel):
    op: Literal["remove"]
    row_id: str
    based_on: dict[str, CellValueBody]


RowEditBody = Annotated[AddRowBody | ChangeRowBody | RemoveRowBody, Field(discriminator="op")]


def _row_edit(body: AddRowBody | ChangeRowBody | RemoveRowBody) -> RowEdit:
    match body:
        case AddRowBody(cells=cells):
            return RowAddition(cells)
        case ChangeRowBody(row_id=row_id, based_on=based_on, cells=cells):
            return RowChange(row_id, based_on, cells)
        case RemoveRowBody(row_id=row_id, based_on=based_on):
            return RowRemoval(row_id, based_on)


def table_row_edits(table: str, rows: Sequence[AddRowBody | ChangeRowBody | RemoveRowBody]) -> TableRowEdits:
    return TableRowEdits(table, tuple(_row_edit(row) for row in rows))


def stated_part(section: SectionEditBody | None, replace: TextReplacementBody | None) -> PartEdit | None:
    """The part edit a document edit states, or `None` where it states none.

    Both at once is not a part edit: which is made first would decide what the other finds.
    """
    if section is not None and replace is not None:
        raise ValueError("The edit states a section and a replacement. Send one part edit in a request.")
    if section is not None:
        return SectionReplacement(tuple(section.heading_path), section.text)
    if replace is not None:
        return TextReplacement(replace.find, replace.replacement, replace.expected_matches)
    return None


def tables_as_served(tables: DocumentTables) -> dict[str, Any]:
    """A document's typed tables as a read serves them: each row's id and its values.

    A row's `values` are what an edit of that row states as `based_on`.
    """
    return {
        "tables": [
            {
                "name": table.spec.name,
                "section": table.section,
                "found": table.found,
                "missing_columns": list(table.missing_columns),
                "undeclared_columns": list(table.undeclared_columns),
                "rows": [
                    {
                        "row_id": row.row_id,
                        "values": row_values(row),
                        "unreadable": {name: cell.unreadable for name, cell in row.cells.items() if cell.unreadable},
                    }
                    for row in table.rows
                ],
            }
            for table in tables.tables
        ]
    }
