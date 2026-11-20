"""What a document type's table declarations say about the tables a document holds.

A filter over one reading — `src.application.artifacts.document_table_rows` — so the verifier and any
later reader of a row cannot disagree about what a cell holds.

**Refusal blocks; narrowing warns.** A document being filled in must stay writable, so everything
that is merely *not there yet* or *not as the declaration asks* is a warning:

* **W162** a declared table is missing from its section
* **W163** a declared column is missing from the table's header
* **W164** the table has a column the declaration does not
* **W165** a row does not satisfy the table's row schema — a required cell empty, a value outside its
  `enum`, `pattern`, bounds or `format`
* **W166** a reference cell links something that is no artifact here, or one the column does not take
* **W167** a row carries no id
* **W168** a row cell names a row its table does not hold
* **W157** a reference column names a term that does not expand — the code a section's own terms use

Two findings are errors, because each leaves something that cannot be *read* rather than something
incomplete:

* **E162** a cell is not readable as its column's type
* **E163** a row id is not of its table's form, or is carried by two rows

W165 is one code for every row-schema violation because it is one check: the row schema compiled from
the declaration, through the validator every attribute schema goes through — where the corresponding
attribute finding, W042, is likewise one code and a warning.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterator
from typing import Any

from src.application.artifacts.document_table_rows import DocumentTables, TypedCell, TypedRow, TypedTable
from src.application.artifacts.document_tables import ColumnSpec
from src.application.artifacts.reference_terms import ReferenceTermVocabulary, TermStatus
from src.application.artifacts.schema import validate_against_schema
from src.domain.verification_findings import Issue, Severity

#: What says a table is not finished, as against not readable. A document is written with these.
_IN_PROGRESS = frozenset({"W162", "W163", "W164", "W165", "W166", "W167", "W168"})


def is_about_a_table_in_progress(issue: Issue) -> bool:
    """Whether *issue* reports a typed table that is incomplete rather than one that cannot be read."""
    return issue.severity == Severity.WARNING and issue.code in _IN_PROGRESS


def _warning(code: str, message: str, loc: str) -> Issue:
    return Issue(Severity.WARNING, code, message, loc)


def _error(code: str, message: str, loc: str) -> Issue:
    return Issue(Severity.ERROR, code, message, loc)


def _row_label(row: TypedRow, ordinal: int) -> str:
    return f"row {row.row_id}" if row.row_id else f"row {ordinal} (no id)"


def _structure(table: TypedTable, loc: str) -> Iterator[Issue]:
    name = table.spec.name
    yield from (
        _warning(
            "W163",
            f"Table '{name}' has no column '{table.spec.column(column).title}'; its cells read empty in every row",
            loc,
        )
        for column in table.missing_columns
    )
    yield from (
        _warning("W164", f"Table '{name}' has a column '{title}' its declaration does not; it is not read", loc)
        for title in table.undeclared_columns
    )


def _row_ids(table: TypedTable, loc: str) -> Iterator[Issue]:
    spec = table.spec
    carried = Counter(row.row_id for row in table.rows if row.row_id)
    for ordinal, row in enumerate(table.rows, start=1):
        if not row.row_id:
            yield _warning(
                "W167",
                f"Table '{spec.name}' row {ordinal} carries no id; nothing can refer to it until it "
                f"has one, such as {spec.row_id(ordinal)}",
                loc,
            )
        elif spec.row_number(row.row_id) is None:
            yield _error(
                "E163",
                f"Table '{spec.name}' row {ordinal}: '{row.row_id}' is not a row id of this table; "
                f"write it as {spec.row_id_prefix} and a number, such as {spec.row_id(ordinal)}",
                loc,
            )
    yield from (
        _error("E163", f"Table '{spec.name}': {count} rows carry the id '{row_id}'; give each its own", loc)
        for row_id, count in carried.items()
        if count > 1
    )


def _named_rows(cell: TypedCell) -> list[str]:
    return [str(row_id) for row_id in cell.value] if isinstance(cell.value, list) else [str(cell.value)]


def _permitted_terms(column: ColumnSpec, vocabulary: ReferenceTermVocabulary) -> list[str]:
    return [term for term in column.reference_terms if vocabulary.status(term) is not TermStatus.UNKNOWN]


def _reference(
    where: str, column: ColumnSpec, cell: TypedCell, vocabulary: ReferenceTermVocabulary, loc: str
) -> Iterator[Issue]:
    yield from (
        _warning("W166", f"{where} column '{column.title}' links {href}, which is no artifact here", loc)
        for href in cell.unresolved
    )
    permitted = _permitted_terms(column, vocabulary)
    taken = " or ".join(vocabulary.label(term) for term in permitted) or "nothing this deployment knows"
    yield from (
        _warning(
            "W166",
            f"{where} column '{column.title}' links {target.name} ({target.kind}, type "
            f"'{target.type_name}'); the column takes {taken}",
            loc,
        )
        for target in cell.targets
        if not any(vocabulary.satisfied_by(term, target) for term in permitted)
    )


def _cells(
    table: TypedTable, tables: DocumentTables, vocabulary: ReferenceTermVocabulary, loc: str
) -> Iterator[Issue]:
    for ordinal, row in enumerate(table.rows, start=1):
        where = f"Table '{table.spec.name}' {_row_label(row, ordinal)}"
        for column in table.spec.columns:
            cell = row.cells[column.name]
            if cell.unreadable:
                yield _error("E162", f"{where} column '{column.title}': {cell.unreadable}", loc)
            elif column.kind == "reference":
                yield from _reference(where, column, cell, vocabulary, loc)
            elif column.kind == "row" and cell.value is not None:
                yield from (
                    _warning(
                        "W168",
                        f"{where} column '{column.title}' names row {row_id}, "
                        f"which table '{column.row_table}' does not hold",
                        loc,
                    )
                    for row_id in _named_rows(cell)
                    if tables.row(column.row_table, row_id) is None
                )


def _row_schema(table: TypedTable, loc: str) -> Iterator[Issue]:
    """Each row against the schema its declaration compiles to.

    A cell that states something is never also reported as a required cell left empty: what is wrong
    with it — unreadable, or linking nothing that resolves — is said by the finding about the cell.
    """
    schema = table.spec.row_schema
    for ordinal, row in enumerate(table.rows, start=1):
        values: dict[str, Any] = {name: cell.value for name, cell in row.cells.items() if cell.value is not None}
        owed = [
            name
            for name in schema["required"]
            if not row.cells[name].is_stated and name not in table.missing_columns
        ]
        yield from (
            _warning("W165", f"Table '{table.spec.name}' {_row_label(row, ordinal)}: {message}", loc)
            for message in validate_against_schema(values, schema | {"required": owed})
        )


def _terms(table: TypedTable, vocabulary: ReferenceTermVocabulary, loc: str) -> Iterator[Issue]:
    yield from (
        _warning(
            "W157",
            f"Unknown {vocabulary.kind_noun(term)} reference term in table '{table.spec.name}' "
            f"column '{column.title}': {term}",
            loc,
        )
        for column in table.spec.columns
        for term in column.reference_terms
        if vocabulary.status(term) is TermStatus.UNKNOWN
    )


def document_table_issues(
    tables: DocumentTables,
    *,
    present_sections: Collection[str],
    vocabulary: ReferenceTermVocabulary,
    loc: str,
) -> list[Issue]:
    """Every finding about the declared tables of one document.

    A table whose section is missing is not reported: the missing section already is, as E154.
    """
    issues: list[Issue] = []
    for table in tables.tables:
        issues.extend(_terms(table, vocabulary, loc))
        if not table.found:
            if table.section in present_sections:
                issues.append(
                    _warning(
                        "W162",
                        f"Section '{table.section}' holds no table '{table.spec.name}': add one headed "
                        f"{' | '.join(table.spec.header)}",
                        loc,
                    )
                )
            continue
        issues.extend(_structure(table, loc))
        issues.extend(_row_ids(table, loc))
        issues.extend(_cells(table, tables, vocabulary, loc))
        issues.extend(_row_schema(table, loc))
    return issues
