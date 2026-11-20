"""Response contracts for the typed tables a document type's section declares.

One pair of models for both places a section is served — the document-type catalog and the schema
file read — because both serve `application.artifacts.document_tables.TableSpec.to_dict`, and two
mirrors of one producer are two places for it to drift from.
"""

from __future__ import annotations

from pydantic import ConfigDict

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


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
    #: An attribute type, or `reference` (a link to an artifact) or `row` (a row of another table).
    type: str
    #: On a `reference` column: the reference terms a linked artifact must satisfy one of.
    to: list[str] | None = None
    #: On a `row` column: the table whose row ids its cells hold.
    table: str | None = None
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
