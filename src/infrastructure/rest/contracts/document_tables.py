"""Response contracts for the typed tables a document type's section declares, and a document holds.

One pair of models for both places a declaration is served — the document-type catalog and the
schema file read — because both serve `application.artifacts.document_tables.TableSpec.to_dict`, and
two mirrors of one producer are two places for it to drift from.

The rows a document holds are served as the reading answers them: each row's id and its values by
column name. Those values are what an edit of the row states as `based_on`, so a client that reads a
row here has what it needs to change it and never reads a markdown table itself.
"""

from __future__ import annotations

from pydantic import ConfigDict

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted
from src.infrastructure.rest.contracts.wire_shape import Closed

#: What a stated cell holds: its column's typed value, an artifact id or row id where the column
#: addresses one, a list where it takes several — or its text as spelled, where no value can be made.
CellValueContract = str | bool | int | float | list[str | bool | int | float]


class DocumentTableColumn(NullsOmitted):
    """One column of a declared table, as the declaration states it with its defaults written out.

    Open, for one reason: a value column is written as a property of an attribute schema is, so the
    keys beside the ones declared here — `enum`, `pattern`, `minimum`, `format`, `items` — are JSON
    Schema's keywords, and this model with `type` is the schema of one cell.
    """

    model_config = ConfigDict(extra="allow")

    name: str
    #: The header cell the column is found under.
    title: str
    required: bool
    #: An attribute type, or `reference` (a link to an artifact), `row` (a row of another table) or `id` (the id
    #: of a stored artifact).
    type: str
    #: On a `reference` column: the reference terms a linked artifact must satisfy one of.
    to: list[str] | None = None
    #: On a `row` column: the table whose row ids its cells hold.
    table: str | None = None
    #: On an `id` column: the kind of artifact whose stored id its cells hold.
    kind: str | None = None
    #: On an `id` column: what a cell may hold instead of an id.
    words: list[str] | None = None
    #: On a `reference` or `row` column: whether a cell may address several.
    many: bool | None = None


class DocumentTableDeclaration(NullsOmitted):
    """One typed table a section holds: its columns, and the form of its rows' ids."""

    name: str
    #: The prefix of a row id, which is the prefix and a number: `S3`.
    row_id: str
    #: The header cell of the id column, which is the table's first.
    row_id_title: str
    columns: list[DocumentTableColumn]


class DocumentTableRow(Closed):
    """One row of a typed table as a document holds it."""

    #: The id in the row's first cell, which addresses it in an edit. Empty when the row carries none.
    row_id: str
    #: Every stated cell's value, by column name. An empty cell has no entry.
    values: dict[str, CellValueContract]
    #: Why a cell could not be read as its column's type, by column name. Its entry in `values` is
    #: then the cell's text as spelled.
    unreadable: dict[str, str]


class DocumentTableRows(Closed):
    """One declared table and the rows this document holds of it."""

    name: str
    section: str
    #: Whether the section holds the table at all. A table not found has no rows to edit.
    found: bool
    #: Declared columns the table's header lacks, by column name.
    missing_columns: list[str]
    #: Header titles that are no declared column's, as written.
    undeclared_columns: list[str]
    rows: list[DocumentTableRow]


class DocumentTablesResponse(Closed):
    """Every table the document's type declares, as this document holds it. Empty for a type that
    declares none."""

    tables: list[DocumentTableRows]
