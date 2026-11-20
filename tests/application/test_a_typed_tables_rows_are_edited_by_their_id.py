"""Rows of a typed table are added, changed and removed by id, and read back as the values written.

The pair under test is `edit_table_rows` and `read_document_tables`. A row is written from typed
values and read back as those values, over what a cell may have to carry; a row is addressed by the
id in its first cell, wherever it stands; and an edit of a row that is no longer what the edit was
based on is refused with the row and both values named.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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
from src.application.artifacts.document_schema import DocumentSchema, normalize_document_schema
from src.application.artifacts.document_table_edits import RowsEdited, edit_table_rows, row_values
from src.application.artifacts.document_table_rows import TypedTable, read_document_tables
from src.application.document_links import as_link
from src.domain.ontology_representation.property_value import encode
from tests.support.typed_table_documents import (
    STRESS_ANALYSIS,
    document_path,
    document_text,
    document_type,
    entity_in,
    link_to,
    repository_in,
    table_of,
    table_text,
)

_NOWHERE = Path("/nowhere/doc.md")

#: Texts a string cell may have to carry, a line break among them.
_PERMITTED_TEXTS = (
    "plain", "a|b", "ends in a pipe|", "back\\slash", "ends in a backslash\\", "---", "source---target",
    "`code | span`", "two\nlines", "true", "12", "ünïcödé ✓",
)

_TYPED_VALUES: tuple[tuple[dict[str, Any], CellValue], ...] = (
    ({"type": "integer"}, -12),
    ({"type": "number"}, 0.25),
    ({"type": "boolean"}, True),
    ({"type": "boolean"}, False),
    ({"type": "array", "items": {"type": "string"}}, ["a|b", "c"]),
    ({"type": "string", "enum": ["H", "M", "L"]}, "M"),
)


def _notes(*columns: dict[str, Any]) -> DocumentSchema:
    table = {"name": "notes", "row_id": "N", "columns": list(columns)}
    return normalize_document_schema(
        "notes", {"abbreviation": "NOTE", "subdirectory": "notes", "sections": [{"name": "Notes", "tables": [table]}]}
    )


_SCHEMA = _notes({"name": "note"}, {"name": "state", "enum": ["open", "done"]}, {"name": "weight", "type": "integer"})


def _document(schema: DocumentSchema = _SCHEMA, rows: list[dict[str, str]] | None = None) -> str:
    held = [{"note": "first", "state": "open"}, {"note": "second"}, {"note": "third", "weight": "3"}]
    return document_text(schema, {"notes": table_text(table_of(schema, "notes"), held if rows is None else rows)})


def _edit(content: str, *edits: RowEdit, schema: DocumentSchema = _SCHEMA, doc_path: Path = _NOWHERE) -> RowsEdited:
    return edit_table_rows(content, TableRowEdits("notes", edits), schema=schema, doc_path=doc_path, link_of=as_link)


def _read(content: str, schema: DocumentSchema = _SCHEMA, doc_path: Path = _NOWHERE) -> TypedTable:
    table = read_document_tables(doc_path, content, schema).table("notes")
    assert table is not None
    return table


def _values(content: str, schema: DocumentSchema = _SCHEMA) -> dict[str, dict[str, CellValue]]:
    return {row.row_id: row_values(row) for row in _read(content, schema).rows}


def _based_on(content: str, row_id: str) -> dict[str, CellValue]:
    row = _read(content).row(row_id)
    assert row is not None
    return row_values(row)


class TestAWrittenCellReadsBackAsItsValue:
    @pytest.mark.parametrize("text", _PERMITTED_TEXTS)
    def test_a_string_in_a_changed_row_and_in_an_added_one(self, text: str) -> None:
        document = _document()

        edited = _edit(
            document,
            RowChange("N2", _based_on(document, "N2"), {"note": text}),
            RowAddition({"note": text, "state": "done"}),
        )

        assert _values(edited.content) == {
            "N1": {"note": "first", "state": "open"},
            "N2": {"note": text},
            "N3": {"note": "third", "weight": 3},
            "N4": {"note": text, "state": "done"},
        }
        assert edited.added_row_ids == ("N4",)

    @pytest.mark.parametrize(("column", "value"), _TYPED_VALUES)
    def test_a_typed_value(self, column: dict[str, Any], value: CellValue) -> None:
        schema = _notes({"name": "before"}, {"name": "typed"} | column, {"name": "after"})
        document = _document(schema, [{"before": "b", "after": "a"}])

        edited = _edit(document, RowChange("N1", {"before": "b", "after": "a"}, {"typed": value}), schema=schema)

        assert _values(edited.content, schema) == {"N1": {"before": "b", "typed": value, "after": "a"}}
        assert _read(edited.content, schema).rows[0].cells["typed"].unreadable == ""

    def test_a_cell_stated_as_nothing_is_emptied(self) -> None:
        document = _document()

        edited = _edit(document, RowChange("N1", _based_on(document, "N1"), {"state": None, "note": ""}))

        assert _values(edited.content)["N1"] == {}

    def test_row_ids_and_references(self, tmp_path: Path) -> None:
        repo = repository_in(tmp_path, STRESS_ANALYSIS)
        schema = document_type(STRESS_ANALYSIS)
        doc = document_path(repo, schema)
        goal = entity_in(repo, "goal", "keep-selling")
        driver = entity_in(repo, "driver", "provider-risk")
        document = document_text(schema, {})

        ended = edit_table_rows(
            document,
            TableRowEdits(
                "end-states",
                (RowAddition({"end_state": "Orders cannot be paid", "affects": [
                    link_to(goal, written_in=doc, label="the|goal"), link_to(driver, written_in=doc)]}),),
            ),
            schema=schema, doc_path=doc, link_of=as_link,
        )
        adapted = edit_table_rows(
            ended.content,
            TableRowEdits("adaptations", (RowAddition({"end_states": ["E1"], "candidate_architecture": "queue"}),)),
            schema=schema, doc_path=doc, link_of=as_link,
        )

        read = read_document_tables(doc, adapted.content, schema)
        (end_state,) = read.table("end-states").rows  # type: ignore[union-attr]
        (adaptation,) = read.table("adaptations").rows  # type: ignore[union-attr]
        assert end_state.cells["affects"].value == [goal.stem, driver.stem]
        assert adaptation.cells["end_states"].value == ["E1"]


class TestARowIsAddressedByItsId:
    def test_wherever_it_stands(self) -> None:
        reordered = document_text(
            _SCHEMA,
            {"notes": table_text(
                table_of(_SCHEMA, "notes"), [{"note": "third"}, {"note": "first"}, {"note": "second"}],
                row_ids=["N3", "N1", "N2"],
            )},
        )

        edited = _edit(
            reordered, RowChange("N1", {"note": "first"}, {"note": "FIRST"}), RowRemoval("N3", {"note": "third"})
        )

        assert [(row.row_id, row.cells["note"].value) for row in _read(edited.content).rows] == [
            ("N1", "FIRST"), ("N2", "second")
        ]

    def test_an_added_row_takes_the_id_after_the_highest_in_use_and_several_take_several(self) -> None:
        sparse = document_text(
            _SCHEMA,
            {"notes": table_text(table_of(_SCHEMA, "notes"), [{"note": "a"}, {"note": "b"}], row_ids=["N7", "N2"])},
        )

        edited = _edit(sparse, RowAddition({"note": "c"}), RowAddition({"note": "d"}))

        assert edited.added_row_ids == ("N8", "N9")
        assert [row.row_id for row in _read(edited.content).rows] == ["N7", "N2", "N8", "N9"]

    def test_an_empty_table_takes_its_first_row(self) -> None:
        edited = _edit(_document(rows=[]), RowAddition({"note": "a"}))

        assert _values(edited.content) == {"N1": {"note": "a"}}

    def test_only_the_changed_rows_line_differs(self) -> None:
        document = _document()

        edited = _edit(document, RowChange("N2", _based_on(document, "N2"), {"state": "done"}))

        before, after = document.split("\n"), edited.content.split("\n")
        assert [(was, now) for was, now in zip(before, after, strict=True) if was != now] == [
            ("| N2 | second | | |", "| N2 | second | done | |")
        ]

    def test_a_column_the_author_added_keeps_its_cell_in_a_changed_row(self) -> None:
        document = document_text(
            _SCHEMA, {"notes": "| Id | Mine | Note | State | Weight |\n|---|---|---|---|---|\n| N1 | kept | a | | |"}
        )

        edited = _edit(document, RowChange("N1", {"note": "a"}, {"note": "b"}), RowAddition({"note": "c"}))

        assert "| N1 | kept | b | | |\n| N2 | | c | | |\n" in edited.content


class TestTwoWritersOnOneTable:
    def test_different_rows_both_succeed_in_either_order(self) -> None:
        document = _document()
        first = RowChange("N1", _based_on(document, "N1"), {"state": "done"})
        second = RowChange("N3", _based_on(document, "N3"), {"weight": 9})

        one_way = _edit(_edit(document, first).content, second).content
        the_other = _edit(_edit(document, second).content, first).content

        assert one_way == the_other
        assert _values(one_way)["N1"]["state"] == "done" and _values(one_way)["N3"]["weight"] == 9

    def test_an_addition_never_meets_another_writers_change(self) -> None:
        document = _document()
        changed = _edit(document, RowChange("N1", _based_on(document, "N1"), {"note": "changed"})).content

        assert _edit(changed, RowAddition({"note": "new"})).added_row_ids == ("N4",)

    def test_the_second_change_of_one_row_is_refused_naming_the_row_and_both_values(self) -> None:
        document = _document()
        read_by_both = _based_on(document, "N1")
        after_the_first = _edit(document, RowChange("N1", read_by_both, {"state": "done"})).content

        with pytest.raises(RowChangedSinceRead) as refused:
            _edit(after_the_first, RowChange("N1", read_by_both, {"note": "mine"}))

        assert str(refused.value) == (
            "Table 'notes' row N1 has changed since it was read: 'state' was \"open\" and is now \"done\". "
            "Read the row again and make the edit on what it holds now."
        )

    def test_a_removal_of_a_row_that_changed_is_refused(self) -> None:
        document = _document()
        read = _based_on(document, "N3")
        changed = _edit(document, RowChange("N3", read, {"weight": None})).content

        with pytest.raises(RowChangedSinceRead, match="row N3 has changed .* 'weight' was 3 and is now nothing"):
            _edit(changed, RowRemoval("N3", read))

    def test_a_change_based_on_less_than_the_row_holds_is_refused(self) -> None:
        with pytest.raises(RowChangedSinceRead, match="'note' was nothing and is now \"first\""):
            _edit(_document(), RowChange("N1", {"state": "open"}, {"state": "done"}))

    def test_one_stale_row_refuses_the_whole_call(self) -> None:
        document = _document()

        with pytest.raises(RowChangedSinceRead):
            _edit(
                document,
                RowChange("N2", _based_on(document, "N2"), {"note": "x"}),
                RowRemoval("N1", {"note": "stale"}),
            )

    def test_true_is_not_one_and_a_cell_the_reading_makes_no_value_of_is_compared_as_spelled(self) -> None:
        schema = _notes({"name": "flag", "type": "boolean"}, {"name": "count", "type": "integer"})
        document = _document(schema, [{"flag": "true", "count": "many"}])

        assert row_values(_read(document, schema).rows[0]) == {"flag": True, "count": "many"}
        with pytest.raises(RowChangedSinceRead, match="'flag' was 1 and is now true"):
            _edit(document, RowRemoval("N1", {"flag": 1, "count": "many"}), schema=schema)
        with pytest.raises(RowChangedSinceRead, match="'count' was \"several\" and is now \"many\""):
            _edit(document, RowRemoval("N1", {"flag": True, "count": "several"}), schema=schema)
        assert _values(_edit(document, RowRemoval("N1", {"flag": True, "count": "many"}), schema=schema).content) == {}


class TestAnEditThatCannotBeMadeIsRefused:
    @pytest.mark.parametrize(
        ("edit", "said"),
        [
            (RowChange("N9", {}, {"note": "x"}), "holds no row 'N9'. It holds: N1, N2, N3."),
            (RowRemoval("S1", {}), "holds no row 'S1'"),
            (RowAddition({"nope": "x"}), "declares no column 'nope'. Its columns are: note, state, weight."),
            (RowAddition({"note": {"a": 1}}), "column 'note' takes a text, a number, true or false"),  # type: ignore[dict-item]
        ],
    )
    def test_with_a_sentence_naming_what_to_change(self, edit: RowEdit, said: str) -> None:
        with pytest.raises(DocumentEditRefused, match=said):
            _edit(_document(), edit)

    def test_a_row_edited_twice_in_one_call(self) -> None:
        document = _document()
        based_on = _based_on(document, "N1")

        with pytest.raises(DocumentEditRefused, match="row N1 is edited more than once in one call"):
            _edit(document, RowChange("N1", based_on, {"note": "x"}), RowRemoval("N1", based_on))

    def test_an_id_two_rows_carry(self) -> None:
        rows = table_text(table_of(_SCHEMA, "notes"), [{"note": "a"}, {"note": "b"}], row_ids=["N1", "N1"])
        twice = document_text(_SCHEMA, {"notes": rows})

        with pytest.raises(DocumentEditRefused, match="2 rows carry the id 'N1', so it addresses none of them"):
            _edit(twice, RowChange("N1", {"note": "a"}, {"note": "x"}))

    def test_a_table_the_type_does_not_declare(self) -> None:
        with pytest.raises(DocumentEditRefused, match="declares no table 'nope'. It declares: notes."):
            edit_table_rows(
                _document(),
                TableRowEdits("nope", (RowAddition({}),)),
                schema=_SCHEMA, doc_path=_NOWHERE, link_of=as_link,
            )

    def test_a_declared_table_the_document_does_not_hold(self) -> None:
        without = document_text(_SCHEMA, {"notes": "No table yet."})

        with pytest.raises(DocumentEditRefused, match=r"Section 'Notes' holds no table 'notes'. Add one headed Id \|"):
            _edit(without, RowAddition({"note": "a"}))

    def test_a_declared_column_the_tables_header_lacks(self) -> None:
        narrow = document_text(_SCHEMA, {"notes": "| Id | Note |\n|---|---|\n| N1 | a |"})

        with pytest.raises(DocumentEditRefused, match="has no column headed 'State' in this document"):
            _edit(narrow, RowChange("N1", {"note": "a"}, {"state": "done"}))

    def test_no_edits(self) -> None:
        with pytest.raises(DocumentEditRefused, match="names no row to add, change or remove"):
            _edit(_document())

    def test_several_rows_for_a_column_that_takes_one(self) -> None:
        schema = document_type(STRESS_ANALYSIS)

        with pytest.raises(DocumentEditRefused, match="column 'end_state' takes one row id, and was given"):
            edit_table_rows(
                document_text(schema, {}),
                TableRowEdits("stressors", (RowAddition({"stressor": "x", "end_state": ["E1", "E2"]}),)),
                schema=schema, doc_path=_NOWHERE, link_of=as_link,
            )


def test_a_value_is_written_as_the_codec_spells_it() -> None:
    """The writer here and the fixture writer agree, so the round trip above is over one codec."""
    document = _document(rows=[])

    edited = _edit(document, RowAddition({"note": "a|b\nc", "weight": 4}))

    assert f"| N1 | {encode('a|b' + chr(10) + 'c')} | | 4 |" in edited.content
