"""A typed table is written through the table owner and read back as the values it was written from.

Stated over what the syntax permits and not over the two example types: a title or a cell may hold a
pipe, a backslash, three hyphens or a link whose label holds a pipe, and none of those appears in
either example. The pair under test is the declaration's scaffold and the codec's cells on one side,
`read_document_tables` on the other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.application.artifacts.document_schema import DocumentSchema, normalize_document_schema
from src.application.artifacts.document_table_rows import TypedTable, read_document_tables
from src.application.artifacts.document_tables import format_row_ids
from src.domain.markdown_table import escape_cell
from src.domain.ontology_representation.property_value import PropertyValue, encode
from tests.support.typed_table_documents import (
    ARCHITECTURE_EVALUATION,
    EXAMPLE_TYPES,
    STRESS_ANALYSIS,
    adr_in,
    document_path,
    document_text,
    document_type,
    entity_in,
    link_to,
    repository_in,
    table_of,
    table_text,
)

#: Titles a header cell may have to carry. Each is one a reading that split a row on every pipe, or
#: took a row of hyphens for the delimiter, would not find again.
_PERMITTED_TITLES = ("Plain", "a|b", "ends in a pipe|", "back\\slash", "ends in a backslash\\", "---", "ünïcödé ✓")

#: Values a string cell may have to carry, a line break among them: the codec spells that one.
_PERMITTED_TEXTS = (*_PERMITTED_TITLES, "two\nlines", "source---target", "`code | span`", "true", "12")

_TYPED_VALUES: tuple[tuple[dict[str, Any], PropertyValue], ...] = (
    ({"type": "integer"}, -12),
    ({"type": "number"}, 0.25),
    ({"type": "boolean"}, True),
    ({"type": "boolean"}, False),
    ({"type": "array", "items": {"type": "string"}}, ["a|b", "c"]),
    ({"type": "string", "enum": ["H", "M", "L"]}, "M"),
)


def _type_with(*columns: dict[str, Any], row_id_title: str = "Id") -> DocumentSchema:
    table = {"name": "notes", "row_id": "N", "row_id_title": row_id_title, "columns": list(columns)}
    return normalize_document_schema(
        "notes", {"abbreviation": "NOTE", "subdirectory": "notes", "sections": [{"name": "Notes", "tables": [table]}]}
    )


def _read(schema: DocumentSchema, tables: dict[str, str], doc_path: Path = Path("/nowhere/doc.md")) -> TypedTable:
    """The first table written, as read back — or the type's first table when none was written."""
    read = read_document_tables(doc_path, document_text(schema, tables), schema)
    written = next(iter(tables), read.tables[0].spec.name)
    return next(table for table in read.tables if table.spec.name == written)


class TestAScaffoldedTableIsTheDeclaredOne:
    @pytest.mark.parametrize("doc_type", EXAMPLE_TYPES)
    def test_every_table_of_an_example_type_is_found_whole_and_empty(self, doc_type: str) -> None:
        schema = document_type(doc_type)

        read = read_document_tables(Path("/nowhere/doc.md"), document_text(schema, {}), schema)

        assert [table.spec.name for table in read.tables] == [
            table.name for section in schema.sections for table in section.tables
        ]
        for table in read.tables:
            assert (table.found, table.rows, table.missing_columns, table.undeclared_columns) == (True, (), (), ())

    @pytest.mark.parametrize("title", _PERMITTED_TITLES)
    def test_a_column_is_found_under_any_title_a_cell_can_carry(self, title: str) -> None:
        schema = _type_with({"name": "note", "title": title}, {"name": "after"})

        table = _read(schema, {"notes": table_text(table_of(schema, "notes"), [{"note": "x", "after": "y"}])})

        assert (table.missing_columns, table.undeclared_columns) == ((), ())
        assert [(row.cells["note"].value, row.cells["after"].value) for row in table.rows] == [("x", "y")]

    @pytest.mark.parametrize("title", _PERMITTED_TITLES)
    def test_a_table_is_found_under_any_row_id_title_a_cell_can_carry(self, title: str) -> None:
        schema = _type_with({"name": "note"}, row_id_title=title)

        assert _read(schema, {}).found


class TestACellReadsBackAsTheValueItWasWrittenFrom:
    @pytest.mark.parametrize("text", _PERMITTED_TEXTS)
    def test_a_string(self, text: str) -> None:
        schema = _type_with({"name": "before"}, {"name": "note"}, {"name": "after"})
        row = {"before": "b", "note": encode(text), "after": "a"}

        (read,) = _read(schema, {"notes": table_text(table_of(schema, "notes"), [row])}).rows

        assert (read.row_id, read.cells["before"].value, read.cells["note"].value, read.cells["after"].value) == (
            "N1",
            "b",
            text,
            "a",
        )

    @pytest.mark.parametrize(("declared", "value"), _TYPED_VALUES)
    def test_a_value_of_each_attribute_type(self, declared: dict[str, Any], value: PropertyValue) -> None:
        schema = _type_with({"name": "note"} | declared)

        (read,) = _read(schema, {"notes": table_text(table_of(schema, "notes"), [{"note": encode(value)}])}).rows

        assert read.cells["note"].value == value
        assert type(read.cells["note"].value) is type(value)
        assert read.cells["note"].unreadable == ""

    def test_an_empty_cell_states_nothing(self) -> None:
        schema = _type_with({"name": "note"}, {"name": "count", "type": "integer"})

        (read,) = _read(schema, {"notes": table_text(table_of(schema, "notes"), [{}])}).rows

        assert [(cell.is_stated, cell.value, cell.unreadable) for cell in read.cells.values()] == [
            (False, None, ""),
            (False, None, ""),
        ]

    @pytest.mark.parametrize(("declared", "cell"), [("integer", "twelve"), ("boolean", "yes"), ("number", "1,5")])
    def test_a_cell_that_is_not_of_its_type_says_so_and_carries_no_value(self, declared: str, cell: str) -> None:
        schema = _type_with({"name": "note", "type": declared})

        (read,) = _read(schema, {"notes": table_text(table_of(schema, "notes"), [{"note": cell}])}).rows

        assert read.cells["note"].value is None
        assert declared in read.cells["note"].unreadable


class TestAReferenceCellReadsBackAsWhatItLinks:
    def test_one_link_resolves_through_the_link_owner(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)
        schema = document_type(STRESS_ANALYSIS)
        doc = document_path(repo, schema)
        requirement = entity_in(repo, "requirement", "survive-a-provider-outage")
        link = escape_cell(link_to(requirement, written_in=doc, label="a|b"))
        row = {"end_state": "Orders queue", "required_behaviour": link}

        table = _read(schema, {"end-states": table_text(table_of(schema, "end-states"), [row])}, doc)

        cell = table.rows[0].cells["required_behaviour"]
        assert cell.value == "ENT@1000000001.surviv.survive-a-provider-outage"
        assert [(target.kind, target.type_name) for target in cell.targets] == [("entity", "requirement")]
        assert (cell.unresolved, cell.unreadable) == ((), "")

    def test_several_links_read_back_in_the_order_written(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)
        schema = document_type(STRESS_ANALYSIS)
        doc = document_path(repo, schema)
        affected = [entity_in(repo, "goal", "keep-selling"), entity_in(repo, "driver", "provider-churn")]
        row = {"end_state": "x", "affects": ", ".join(link_to(target, written_in=doc) for target in affected)}

        table = _read(schema, {"end-states": table_text(table_of(schema, "end-states"), [row])}, doc)

        assert table.rows[0].cells["affects"].value == [
            "ENT@1000000001.keep-s.keep-selling",
            "ENT@1000000001.provid.provider-churn",
        ]

    def test_a_document_is_a_target_as_an_entity_is(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, ARCHITECTURE_EVALUATION)
        schema = document_type(ARCHITECTURE_EVALUATION)
        doc = document_path(repo, schema)
        row = {"scenario": "U1", "decision": link_to(adr_in(repo, "queue-orders"), written_in=doc)}

        table = read_document_tables(
            doc, document_text(schema, {"analysis": table_text(table_of(schema, "analysis"), [row])}), schema
        ).table("analysis")

        assert table is not None
        assert [(target.kind, target.type_name) for target in table.rows[0].cells["decision"].targets] == [
            ("document", "adr")
        ]

    def test_a_link_to_nothing_is_kept_apart_from_what_resolved(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)
        schema = document_type(STRESS_ANALYSIS)
        row = {"end_state": "x", "required_behaviour": "[gone](../../model/requirement/gone.md)"}

        table = _read(
            schema, {"end-states": table_text(table_of(schema, "end-states"), [row])}, document_path(repo, schema)
        )

        cell = table.rows[0].cells["required_behaviour"]
        assert (cell.value, cell.targets, cell.unresolved) == (None, (), ("../../model/requirement/gone.md",))

    @pytest.mark.parametrize(
        ("cell", "says"),
        [("the outage requirement", "holds none"), ("[a](a.md) and [b](b.md)", "holds 2")],
    )
    def test_a_cell_that_is_not_one_link_cannot_be_read_as_a_reference(self, cell: str, says: str) -> None:
        schema = document_type(STRESS_ANALYSIS)
        row = {"end_state": "x", "required_behaviour": cell}

        table = _read(schema, {"end-states": table_text(table_of(schema, "end-states"), [row])})

        assert says in table.rows[0].cells["required_behaviour"].unreadable


class TestARowCellReadsBackAsTheRowsItNames:
    def test_one_row_and_several(self) -> None:
        schema = document_type(STRESS_ANALYSIS)
        tables = {
            "end-states": table_text(table_of(schema, "end-states"), [{"end_state": "a"}, {"end_state": "b"}]),
            "stressors": table_text(table_of(schema, "stressors"), [{"stressor": "s", "end_state": "E2"}]),
            "adaptations": table_text(
                table_of(schema, "adaptations"), [{"end_states": escape_cell(format_row_ids(["E1", "E2"]))}]
            ),
        }

        read = read_document_tables(Path("/nowhere/doc.md"), document_text(schema, tables), schema)

        stressor, adaptation = read.table("stressors"), read.table("adaptations")
        assert stressor is not None and adaptation is not None
        assert stressor.rows[0].cells["end_state"].value == "E2"
        assert adaptation.rows[0].cells["end_states"].value == ["E1", "E2"]
        named = read.row("end-states", "E2")
        assert named is not None and named.cells["end_state"].value == "b"
        assert read.row("end-states", "E3") is None

    @pytest.mark.parametrize("cell", ["the second one", "E1 E2", "e1"])
    def test_a_cell_that_is_not_a_row_id_cannot_be_read_as_one(self, cell: str) -> None:
        schema = document_type(STRESS_ANALYSIS)
        tables = {"stressors": table_text(table_of(schema, "stressors"), [{"stressor": "s", "end_state": cell}])}

        table = read_document_tables(Path("/nowhere/doc.md"), document_text(schema, tables), schema).table("stressors")

        assert table is not None
        assert table.rows[0].cells["end_state"].value is None
        assert "one row id" in table.rows[0].cells["end_state"].unreadable


class TestAHandEditedTableIsStillRead:
    """As tolerant as the table owner is, and no further."""

    _SCHEMA = _type_with({"name": "note"}, {"name": "count", "type": "integer"})

    def _table(self, text: str) -> TypedTable:
        return _read(self._SCHEMA, {"notes": text})

    def test_columns_in_another_order_are_read_by_their_titles(self) -> None:
        table = self._table("| Id | Count | Note |\n|---|---|---|\n| N1 | 3 | three |")

        assert (table.rows[0].cells["note"].value, table.rows[0].cells["count"].value) == ("three", 3)

    def test_padding_alignment_and_missing_outer_pipes_do_not_matter(self) -> None:
        table = self._table("Id   |  Note  | Count\n:--|:-:|--:\n N7 |  seven  |  7  ")

        assert [(row.row_id, row.cells["note"].value, row.cells["count"].value) for row in table.rows] == [
            ("N7", "seven", 7)
        ]

    def test_a_removed_column_reads_empty_and_is_named(self) -> None:
        table = self._table("| Id | Note |\n|---|---|\n| N1 | one |")

        assert table.missing_columns == ("count",)
        assert table.rows[0].cells["count"].is_stated is False

    def test_an_added_column_is_named_and_not_read(self) -> None:
        table = self._table("| Id | Note | Owner | Count | Note |\n|---|---|---|---|---|\n| N1 | one | me | 1 | more |")

        assert table.undeclared_columns == ("Owner", "Note")
        assert (table.rows[0].cells["note"].value, table.rows[0].cells["count"].value) == ("one", 1)

    def test_a_row_without_an_id_is_still_a_row(self) -> None:
        table = self._table("| Id | Note | Count |\n|---|---|---|\n| | later | |")

        assert [(row.row_id, row.cells["note"].value) for row in table.rows] == [("", "later")]

    def test_a_table_of_the_authors_own_beside_it_is_left_alone(self) -> None:
        own = "| Term | Meaning |\n|---|---|\n| N1 | not a row of ours |"
        declared = "| Id | Note | Count |\n|---|---|---|\n| N1 | ours | 1 |"

        table = self._table(f"{own}\n\nSome prose between.\n\n{declared}")

        assert [row.cells["note"].value for row in table.rows] == ["ours"]

    def test_a_section_without_the_table_says_it_was_not_found(self) -> None:
        table = self._table("Nothing tabular yet.")

        assert (table.found, table.rows) == (False, ())
