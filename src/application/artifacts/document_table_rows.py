"""A document's typed tables, read into rows of typed values.

Given a document and its type, each table the type declares
(`src.application.artifacts.document_tables`) is answered with its rows: every row's id, and every
cell as the value its column's type makes of it. Reading reports and never refuses — a cell that
cannot be read says why and carries no value, a column the header lacks reads empty in every row —
so that what the verifier says about a document and what a later reader is given are one reading.

Nothing here decides a syntax of its own. Where a table is and what its cells are is
`src.domain.markdown_table`'s; a value cell is decoded by the typed-property codec; a link, and what
it resolves to, is `src.application.document_links`'s; a row id's form is the declaration's.

**Which table of a section is the declared one** is said by its first header cell: the declaration's
row-id title. Any other table in the section is the author's own and is left alone.

**A cell that states nothing has no value.** An empty cell is unstated rather than an empty string,
as an empty attribute cell is to the verifier.

**Where a table stands is part of the reading.** A table found is answered with the lines it occupies
in the document's body, so that a row is edited in the table this reading found and no other.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from src.application.artifacts.document_schema import DocumentSchema, get_document_schema_object
from src.application.artifacts.document_sections import document_body, document_sections
from src.application.artifacts.document_tables import ColumnSpec, TableSpec, row_ids_in
from src.application.document_links import ResolvedArtifactLink, iter_markdown_links, resolve_artifact_links
from src.domain.artifact_id import is_entity_id, parse_entity_id
from src.domain.markdown_table import MarkdownTable, tables_in, text_lines, unescape_cell
from src.domain.ontology_representation.property_value import PropertyValue, decode_lenient
from src.domain.repository.artifact_location import ArtifactKindName, own_id_prefix


@dataclass(frozen=True)
class TypedCell:
    """One cell: what is written, and what its column's type makes of it."""

    spelled: str
    #: The typed value: a value column's decoded value, a reference column's artifact id, a row
    #: column's row id — a list of them for a `many` column — or an id column's id or word, as written.
    #: `None` when the cell states nothing, cannot be read, or links nothing that resolves.
    value: PropertyValue | None = None
    #: Why the cell cannot be read as its column's type. Empty when it can.
    unreadable: str = ""
    #: A reference cell's links that resolve to an artifact, as the link owner classifies them.
    targets: tuple[ResolvedArtifactLink, ...] = ()
    #: A reference cell's hrefs that resolve to no artifact.
    unresolved: tuple[str, ...] = ()

    @property
    def is_stated(self) -> bool:
        return bool(self.spelled)


_UNSTATED = TypedCell(spelled="")


@dataclass(frozen=True)
class TypedRow:
    #: The id as written. Empty when the row carries none.
    row_id: str
    #: One cell per declared column, by column name; unstated where the header lacks the column.
    cells: Mapping[str, TypedCell]


@dataclass(frozen=True)
class TypedTable:
    """One declared table as a document holds it."""

    section: str
    spec: TableSpec
    #: Whether the section holds a table headed by this declaration's row-id title.
    found: bool
    rows: tuple[TypedRow, ...] = ()
    #: Declared columns the header lacks, by name.
    missing_columns: tuple[str, ...] = ()
    #: Header titles that are no declared column's, as written.
    undeclared_columns: tuple[str, ...] = ()
    #: The table as the table owner read it, its lines counted in the document's body.
    held: MarkdownTable | None = None
    #: Each declared column's position among the header's cells, by column name, where it has one.
    positions: Mapping[str, int] = field(default_factory=dict)

    def row(self, row_id: str) -> TypedRow | None:
        """The first row carrying `row_id`, or `None` when there is none."""
        return next((row for row in self.rows if row.row_id == row_id), None)


@dataclass(frozen=True)
class DocumentTables:
    """Every table a document's type declares, read from that document."""

    tables: tuple[TypedTable, ...] = ()

    def table(self, name: str) -> TypedTable | None:
        return next((table for table in self.tables if table.spec.name == name), None)

    def row(self, table: str, row_id: str) -> TypedRow | None:
        """The row a row column's cell names, or `None` when the table holds no such row."""
        held = self.table(table)
        return held.row(row_id) if held else None


def _value_cell(column: ColumnSpec, spelled: str) -> TypedCell:
    value, problem = decode_lenient(spelled, dict(column.value_schema))
    return TypedCell(spelled, unreadable=problem) if problem else TypedCell(spelled, value=value)


def _reference_cell(column: ColumnSpec, spelled: str, doc_path: Path) -> TypedCell:
    text = unescape_cell(spelled)
    links = iter_markdown_links(text)
    if not links:
        return TypedCell(spelled, unreadable="a reference cell holds a markdown link, and this one holds none")
    if len(links) > 1 and not column.many:
        return TypedCell(spelled, unreadable=f"the column takes one reference, and the cell holds {len(links)}")
    targets = tuple(resolve_artifact_links(doc_path, text))
    resolved = {target.href for target in targets}
    artifact_ids: list[str | int | float | bool] = [target.artifact_id for target in targets]
    return TypedCell(
        spelled,
        value=(artifact_ids if column.many else artifact_ids[0]) if artifact_ids else None,
        targets=targets,
        unresolved=tuple(link.href for link in links if link.href not in resolved),
    )


def _row_cell(column: ColumnSpec, spelled: str) -> TypedCell:
    named = row_ids_in(unescape_cell(spelled), many=column.many)
    if named is None:
        expected = "row ids separated by commas" if column.many else "one row id"
        return TypedCell(spelled, unreadable=f"the column takes {expected}, such as S3")
    return TypedCell(spelled, value=list(named) if column.many else named[0])


def _names_one_of(text: str, kind: ArtifactKindName | None) -> bool:
    """Whether *text* is an id, in either spelling, of an artifact of *kind*."""
    return kind is not None and is_entity_id(text) and parse_entity_id(text).prefix == own_id_prefix(kind)


def _id_cell(column: ColumnSpec, spelled: str) -> TypedCell:
    """An id of the column's kind, or one of its words. Whether such an artifact is stored is the verifier's."""
    named = unescape_cell(spelled).strip()
    if named in column.words or _names_one_of(named, column.id_kind):
        return TypedCell(spelled, value=named)
    instead = f", or {' or '.join(column.words)}" if column.words else ""
    return TypedCell(spelled, unreadable=f"the column takes the id of a {column.id_kind}{instead}")


def _cell(column: ColumnSpec, spelled: str, doc_path: Path) -> TypedCell:
    if not spelled:
        return _UNSTATED
    match column.kind:
        case "reference":
            return _reference_cell(column, spelled, doc_path)
        case "row":
            return _row_cell(column, spelled)
        case "id":
            return _id_cell(column, spelled)
        case _:
            return _value_cell(column, spelled)


def _declared_table(spec: TableSpec, held: tuple[MarkdownTable, ...]) -> MarkdownTable | None:
    return next((table for table in held if unescape_cell(table.header[0]) == spec.row_id_title), None)


def _read_table(section: str, spec: TableSpec, held: tuple[MarkdownTable, ...], doc_path: Path) -> TypedTable:
    table = _declared_table(spec, held)
    if table is None:
        return TypedTable(section=section, spec=spec, found=False)
    titles = [unescape_cell(cell) for cell in table.header[1:]]
    # The first column so titled is the column; a second is no declared column's.
    position: dict[str, int] = {}
    for at, title in enumerate(titles, start=1):
        position.setdefault(title, at)
    declared = {column.title for column in spec.columns}
    return TypedTable(
        section=section,
        spec=spec,
        found=True,
        rows=tuple(
            TypedRow(
                row_id=unescape_cell(cells[0]),
                cells={
                    column.name: _cell(column, cells[position[column.title]], doc_path)
                    if column.title in position
                    else _UNSTATED
                    for column in spec.columns
                },
            )
            for cells in table.rows
        ),
        missing_columns=tuple(column.name for column in spec.columns if column.title not in position),
        held=table,
        positions={column.name: position[column.title] for column in spec.columns if column.title in position},
        undeclared_columns=tuple(
            title for at, title in enumerate(titles, start=1) if title not in declared or position[title] != at
        ),
    )


def _tables_by_section(body: str) -> dict[str, tuple[MarkdownTable, ...]]:
    """Every table of `body` under the name of its section, its lines counted in `body`.

    Sections sharing a name hold their tables together, in the order the sections stand.
    """
    held: dict[str, tuple[MarkdownTable, ...]] = {}
    for section in document_sections(body):
        lines_before = len(text_lines(body[: section.start]))
        held[section.name] = (
            *held.get(section.name, ()),
            *(
                replace(table, first_line=table.first_line + lines_before)
                for table in tables_in(body[section.start : section.end])
            ),
        )
    return held


def read_document_tables(doc_path: Path, content: str, schema: DocumentSchema) -> DocumentTables:
    """The tables `schema` declares, as the document at `doc_path` with `content` holds them.

    `doc_path` is where the document is, or will be: a reference cell's link is read against it.
    """
    if not any(section.tables for section in schema.sections):
        return DocumentTables()
    held = _tables_by_section(document_body(content))
    return DocumentTables(
        tuple(
            _read_table(section.name, spec, held.get(section.name, ()), doc_path)
            for section in schema.sections
            for spec in section.tables
        )
    )


def tables_of_stored_document(doc_path: Path, doc_type: str, repo_roots: Sequence[Path]) -> DocumentTables:
    """The typed tables of the document stored at `doc_path`, as the first of `repo_roots` that
    declares `doc_type` declares them. No tables where none declares the type."""
    schema = next(
        (declared for root in repo_roots if (declared := get_document_schema_object(root, doc_type)) is not None),
        None,
    )
    if schema is None:
        return DocumentTables()
    return read_document_tables(doc_path, doc_path.read_text(encoding="utf-8"), schema)
