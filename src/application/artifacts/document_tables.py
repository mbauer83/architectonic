"""The typed tables a document type's section declares, and the form of a row's id.

A section entry of a document type may carry `tables`: each a name, a row-id prefix and columns.

    { "name": "Stressors", "tables": [ { "name": "stressors", "row_id": "S", "columns": [
        { "name": "stressor", "required": true },
        { "name": "set", "enum": ["design", "test"], "required": true },
        { "name": "plausible", "type": "boolean" },
        { "name": "end_state", "type": "row", "table": "end-states" },
        { "name": "affects", "type": "reference", "to": ["goal", "driver"], "many": true } ] } ] }

**A column is an attribute.** Apart from `name`, `title` and `required`, a value column is written
exactly as a property of an attribute schema is — `type` from the typed-property codec's vocabulary
(`src.domain.ontology_representation.property_value`), and any JSON Schema keyword beside it: `enum`,
`pattern`, `minimum`, `format`. A cell is decoded by that codec and a row is validated by the
validator every attribute schema goes through, against the row schema compiled here. There is no
second type vocabulary and no second validator.

**Two column types are not attribute types**, because their cells address something. `reference`
takes `to`, a list of reference terms (`src.application.artifacts.reference_terms`), and its cell is a
markdown link. `row` takes `table`, another table of the same document type, and its cell is that
table's row id. Either may be `many`. A row is not a fourth kind of reference term: a term names what
a *link* resolves to, and a row is not a file.

**A row's id is the first column**, written `<prefix><number>` — `S3`. In the table, because an id
kept anywhere else (a comment, an anchor, the row's position) is lost or moved by the first hand edit;
a prefix, so that an id says which table it belongs to and prefixes are distinct across one document
type; a number, so that the next id is one more than the highest and never a reuse of a deleted one.
The column's header is `row_id_title`, `Id` unless stated, and it is what says which table of a
section is the declared one — so two tables of one section state different titles.

The declaration itself is checked by a JSON Schema, through the same validator.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from src.application.artifacts.schema import validate_against_schema
from src.domain.markdown_table import escape_cell, format_table
from src.domain.ontology_representation.property_value import SUPPORTED_SCHEMA_TYPES

TABLES_KEY = "tables"

ColumnKind = Literal["value", "reference", "row"]

REFERENCE_COLUMN_TYPE = "reference"
ROW_COLUMN_TYPE = "row"
DEFAULT_ROW_ID_TITLE = "Id"

#: The keys of a column that are this module's. Every other key of a value column is JSON Schema's.
_COLUMN_KEYS = frozenset({"name", "title", "required", "to", "table", "many"})

_ROW_ID_PREFIX = r"[A-Z][A-Za-z]*"
_ROW_ID = re.compile(rf"({_ROW_ID_PREFIX})([1-9][0-9]*)")

#: What separates the row ids of a `many` cell.
_ROW_ID_SEPARATOR = ","

_NAME = {"type": "string", "pattern": r"^[a-z][a-z0-9_-]*$"}
#: One line that a table cell reads back whole: nothing a cell's trimming would remove.
_TITLE = {"type": "string", "pattern": r"^\S([^\r\n]*\S)?$"}


#: The key each addressing column type states, and no other column type may.
_KEY_OF_TYPE = {REFERENCE_COLUMN_TYPE: "to", ROW_COLUMN_TYPE: "table"}

_COLUMN_DECLARATION: dict[str, Any] = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": _NAME,
        "title": _TITLE,
        "required": {"type": "boolean"},
        "type": {"enum": [*sorted(SUPPORTED_SCHEMA_TYPES), REFERENCE_COLUMN_TYPE, ROW_COLUMN_TYPE]},
        "to": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "table": _NAME,
        "many": {"type": "boolean"},
    },
}

_TABLES_DECLARATION: dict[str, Any] = {
    "type": "object",
    "properties": {
        TABLES_KEY: {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "row_id", "columns"],
                "additionalProperties": False,
                "properties": {
                    "name": _NAME,
                    "row_id": {"type": "string", "pattern": f"^{_ROW_ID_PREFIX}$"},
                    "row_id_title": _TITLE,
                    "columns": {"type": "array", "minItems": 1, "items": _COLUMN_DECLARATION},
                },
            },
        }
    },
}


@dataclass(frozen=True)
class ColumnSpec:
    """One declared column. Which of the three kinds it is follows from what it carries."""

    name: str
    title: str
    required: bool = False
    #: A value column's cell, as a JSON Schema property descriptor in the attribute vocabulary.
    value_schema: Mapping[str, Any] = field(default_factory=dict)
    #: A reference column's permitted targets, as reference terms.
    reference_terms: tuple[str, ...] = ()
    #: A row column's target table.
    row_table: str = ""
    many: bool = False

    @property
    def kind(self) -> ColumnKind:
        if self.reference_terms:
            return "reference"
        return "row" if self.row_table else "value"

    @property
    def cell_schema(self) -> dict[str, Any]:
        """The JSON Schema the value read from one cell satisfies."""
        if self.kind == "value":
            return dict(self.value_schema)
        addressed = {"type": "string"}
        return {"type": "array", "items": addressed} if self.many else addressed

    def to_dict(self) -> dict[str, Any]:
        """The column as a declaration states it, defaults written out."""
        stated: dict[str, Any] = {"name": self.name, "title": self.title, "required": self.required}
        match self.kind:
            case "reference":
                stated |= {"type": REFERENCE_COLUMN_TYPE, "to": list(self.reference_terms), "many": self.many}
            case "row":
                stated |= {"type": ROW_COLUMN_TYPE, "table": self.row_table, "many": self.many}
            case _:
                stated |= self.value_schema
        return stated


@dataclass(frozen=True)
class TableSpec:
    """One declared table: its columns, and the ids its rows carry."""

    name: str
    row_id_prefix: str
    columns: tuple[ColumnSpec, ...]
    row_id_title: str = DEFAULT_ROW_ID_TITLE

    @property
    def header(self) -> tuple[str, ...]:
        """The titles of the header row: the row id's, then each column's."""
        return (self.row_id_title, *(column.title for column in self.columns))

    @property
    def row_schema(self) -> dict[str, Any]:
        """The JSON Schema one row's read values satisfy, by column name."""
        return {
            "type": "object",
            "properties": {column.name: column.cell_schema for column in self.columns},
            "required": [column.name for column in self.columns if column.required],
        }

    def column(self, name: str) -> ColumnSpec:
        return next(column for column in self.columns if column.name == name)

    def row_id(self, number: int) -> str:
        """The id of this table's `number`-th row, counted from one."""
        if number < 1:
            raise ValueError(f"A row id counts from one; {number} names no row of table '{self.name}'")
        return f"{self.row_id_prefix}{number}"

    def row_number(self, row_id: str) -> int | None:
        """The number `row_id` carries, or `None` when it is not an id of this table."""
        match = _ROW_ID.fullmatch(row_id)
        return int(match.group(2)) if match and match.group(1) == self.row_id_prefix else None

    def scaffold(self) -> str:
        """The table with no rows, as the table owner writes it."""
        return format_table([escape_cell(title) for title in self.header], [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "row_id": self.row_id_prefix,
            "row_id_title": self.row_id_title,
            "columns": [column.to_dict() for column in self.columns],
        }


def format_row_ids(row_ids: Iterable[str]) -> str:
    """The cell text naming several rows."""
    return f"{_ROW_ID_SEPARATOR} ".join(row_ids)


def row_ids_in(text: str, *, many: bool) -> tuple[str, ...] | None:
    """The row ids a cell's text names, or `None` when some part of it is not a row id."""
    named = tuple(part.strip() for part in text.split(_ROW_ID_SEPARATOR)) if many else (text.strip(),)
    return named if all(_ROW_ID.fullmatch(row_id) for row_id in named) else None


def _default_title(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").capitalize()


def _column_from(raw: Mapping[str, Any]) -> ColumnSpec:
    name = str(raw["name"])
    column_type = str(raw.get("type", "string"))
    return ColumnSpec(
        name=name,
        title=str(raw.get("title") or _default_title(name)),
        required=bool(raw.get("required", False)),
        value_schema=(
            {}
            if column_type in (REFERENCE_COLUMN_TYPE, ROW_COLUMN_TYPE)
            else {"type": column_type} | {key: value for key, value in raw.items() if key not in _COLUMN_KEYS}
        ),
        reference_terms=tuple(str(term) for term in raw.get("to", ())),
        row_table=str(raw.get("table", "")),
        many=bool(raw.get("many", False)),
    )


def _table_from(raw: Mapping[str, Any]) -> TableSpec:
    return TableSpec(
        name=str(raw["name"]),
        row_id_prefix=str(raw["row_id"]),
        columns=tuple(_column_from(column) for column in raw["columns"]),
        row_id_title=str(raw.get("row_id_title") or DEFAULT_ROW_ID_TITLE),
    )


def _repeated(values: Iterable[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _misplaced_keys(table: Mapping[str, Any]) -> Iterator[str]:
    """Keys that belong to another column type, or are missing from this one.

    Said here and not in the declaration's JSON Schema, which can state the rule and cannot state it
    in words that name the fix.
    """
    for column in table["columns"]:
        column_type = column.get("type", "string")
        where = f"table {table['name']!r} column {column['name']!r}"
        for owner, key in _KEY_OF_TYPE.items():
            if column_type == owner and key not in column:
                yield f"{where}: a {owner} column states `{key}`"
            if column_type != owner and key in column:
                yield f"{where}: `{key}` is a {owner} column's; give the column that type or remove the key"
        if "many" in column and column_type not in _KEY_OF_TYPE:
            yield f"{where}: only a reference or a row column may be `many`; a value column of several is an array"


def _inconsistencies(by_section: Sequence[tuple[TableSpec, ...]]) -> list[str]:
    """What the declaration's JSON Schema does not say: names are distinct, a row column's table exists."""
    tables = [table for section in by_section for table in section]
    names = {table.name for table in tables}
    return [
        *(f"table name {name!r} is declared more than once" for name in _repeated(t.name for t in tables)),
        *(
            f"row_id prefix {prefix!r} is declared more than once, and an id must say which table it is of"
            for prefix in _repeated(t.row_id_prefix for t in tables)
        ),
        *(
            f"two tables of one section are both headed {title!r}; give one a row_id_title"
            for section in by_section
            for title in _repeated(t.row_id_title for t in section)
        ),
        *(
            f"table {table.name!r}: column name {name!r} is declared more than once"
            for table in tables
            for name in _repeated(column.name for column in table.columns)
        ),
        *(
            f"table {table.name!r}: two columns are titled {title!r}"
            for table in tables
            for title in _repeated(table.header)
        ),
        *(
            f"table {table.name!r}: column {column.name!r} takes rows of {column.row_table!r}, "
            "which this document type does not declare"
            for table in tables
            for column in table.columns
            if column.kind == "row" and column.row_table not in names
        ),
    ]


def table_declarations(doc_type: str, sections: Sequence[Mapping[str, Any]]) -> tuple[tuple[TableSpec, ...], ...]:
    """Each section's declared tables, in the order the sections were given.

    Raises `ValueError` naming the document type and everything wrong with its declaration.
    """
    stated = [{TABLES_KEY: section[TABLES_KEY]} if TABLES_KEY in section else {} for section in sections]
    malformed = [
        f"section {index + 1}: {message}"
        for index, section in enumerate(stated)
        for message in validate_against_schema(section, _TABLES_DECLARATION)
    ]
    if malformed:
        raise ValueError(f"Doc-type {doc_type!r}: malformed table declaration — {'; '.join(malformed)}")
    declared = [raw for section in stated for raw in section.get(TABLES_KEY, ())]
    misplaced = [problem for raw in declared for problem in _misplaced_keys(raw)]
    if misplaced:
        raise ValueError(f"Doc-type {doc_type!r}: malformed table declaration — {'; '.join(misplaced)}")
    by_section = tuple(tuple(_table_from(raw) for raw in section.get(TABLES_KEY, ())) for section in stated)
    inconsistent = _inconsistencies(by_section)
    if inconsistent:
        raise ValueError(f"Doc-type {doc_type!r}: inconsistent table declaration — {'; '.join(inconsistent)}")
    return by_section
