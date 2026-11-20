"""Rows of a table are rewritten, removed and added in place, and the reader finds what was written.

The pair under test is `with_rows` and `tables_in`: one writes into a text that already holds a
table, the other reads the result. Stated over what the syntax permits a hosting text and a cell to
be — padded and aligned delimiter rows, rows without their outer pipes, trailing whitespace, a table
straight under a heading, a table that ends the file with and without a line ending, carriage
returns — and not over the compact form this project's own writer emits, in which none of those
occurs.

Two things are asserted of every edit: the reader finds exactly the rows the edit describes, and
every line the edit did not address is the line it was, ending included.
"""

from __future__ import annotations

import re

import pytest

from src.domain.markdown_table import MarkdownTable, escape_cell, format_row, tables_in, unescape_cell, with_rows

#: Plain texts a cell may have to carry.
_PERMITTED_TEXTS = (
    "plain",
    "",
    "a|b",
    "ends in a pipe|",
    "back\\slash",
    "ends in a backslash\\",
    "`code | span`",
    "`a\\|b` and `c|d`",
    "source---target",
    "---",
    "[a link|with a pipe](target.md)",
    "ünïcödé ✓",
)

_COMPACT = "| Id | Note | State |\n|---|---|---|\n| N1 | first | open |\n| N2 | second | |\n| N3 | a\\|b | done |\n"

#: Texts holding one three-column table of three rows, as an author may have written it.
_HOSTS: dict[str, str] = {
    "compact": _COMPACT,
    "aligned-and-padded": (
        "| Id  | Note     | State |\n| :-- | :------: | ----: |\n| N1  | first    | open  |\n"
        "| N2  | second   |       |\n| N3  | a\\|b     | done  |\n"
    ),
    "no-outer-pipes": "Id | Note | State\n--- | --- | ---\nN1 | first | open\nN2 | second |\nN3 | a\\|b | done\n",
    "trailing-whitespace": (
        "| Id | Note | State |  \n|---|---|---| \t\n| N1 | first | open |   \n"
        "| N2 | second | |\t\n| N3 | a\\|b | done | \n"
    ),
    "directly-under-a-heading": "## Notes\n" + _COMPACT + "\n## After\n\ntext\n",
    "at-end-of-file-without-a-line-ending": "intro\n\n" + _COMPACT.rstrip("\n"),
    "at-end-of-file-with-one": "intro\n\n" + _COMPACT,
    "carriage-returns": ("intro\r\n\r\n" + _COMPACT + "\r\nafter\r\n").replace("\n", "\r\n").replace("\r\r", "\r"),
    "indented": "- item\n\n  | Id | Note | State |\n  |---|---|---|\n  | N1 | first | open |\n"
    "  | N2 | second | |\n  | N3 | a\\|b | done |\n\nafter\n",
    "between-other-tables": (
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        + _COMPACT
        + "\n```\n| not | a table |\n|---|---|\n```\n\n| C |\n|---|\n| 3 |\n"
    ),
    "ended-by-a-comment": _COMPACT + "<!-- §notes -->\ntext\n",
}

_LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+")


def _lines(text: str) -> list[str]:
    """The lines of `text` with their endings — this test's own split, so the writer is not its own witness."""
    return _LINE.findall(text)


def _the_table(text: str) -> MarkdownTable:
    return next(table for table in tables_in(text) if table.header[0] == "Id")


def _plain(table: MarkdownTable) -> list[list[str]]:
    return [[unescape_cell(cell) for cell in row] for row in table.rows]


_ORIGINAL = [["N1", "first", "open"], ["N2", "second", ""], ["N3", "a|b", "done"]]


@pytest.fixture(params=sorted(_HOSTS), ids=sorted(_HOSTS))
def host(request: pytest.FixtureRequest) -> str:
    return _HOSTS[request.param]


class TestTheHostsAreWhatTheyClaim:
    def test_the_table_is_read_from_every_host(self, host: str) -> None:
        assert _plain(_the_table(host)) == _ORIGINAL

    def test_an_edit_of_nothing_changes_nothing(self, host: str) -> None:
        assert with_rows(host, _the_table(host)) == host


class TestAChangedRowReadsBack:
    @pytest.mark.parametrize("text", _PERMITTED_TEXTS)
    @pytest.mark.parametrize("row", [0, 1, 2])
    def test_the_row_holds_what_was_written_and_the_others_what_they_held(self, host: str, text: str, row: int) -> None:
        table = _the_table(host)

        edited = with_rows(host, table, changed={row: (table.rows[row][0], escape_cell(text), "x")})

        expected = [list(cells) for cells in _ORIGINAL]
        expected[row] = [_ORIGINAL[row][0], text, "x"]
        assert _plain(_the_table(edited)) == expected

    @pytest.mark.parametrize("row", [0, 1, 2])
    def test_every_other_line_is_the_line_it_was(self, host: str, row: int) -> None:
        table = _the_table(host)
        changed_line = table.first_line + 2 + row

        edited = with_rows(host, table, changed={row: ("N9", "`x \\| y`", "")})

        before, after = _lines(host), _lines(edited)
        assert len(after) == len(before)
        assert [at for at, (was, now) in enumerate(zip(before, after, strict=True)) if was != now] == [changed_line]

    def test_a_rewritten_row_keeps_its_line_ending_and_its_indentation(self, host: str) -> None:
        table = _the_table(host)
        line = table.first_line + 2

        edited = with_rows(host, table, changed={0: ("N1", "new", "open")})

        was, now = _lines(host)[line], _lines(edited)[line]
        indentation, ending = was[: len(was) - len(was.lstrip())], was[len(was.rstrip("\r\n")) :]
        assert now == indentation + format_row(["N1", "new", "open"]) + ending


class TestARemovedRowIsGone:
    @pytest.mark.parametrize("rows", [{0}, {1}, {2}, {0, 2}, {0, 1, 2}])
    def test_the_other_rows_read_back_and_every_other_line_is_the_line_it_was(self, host: str, rows: set[int]) -> None:
        table = _the_table(host)
        removed_lines = {table.first_line + 2 + row for row in rows}

        edited = with_rows(host, table, removed=rows)

        assert _plain(_the_table(edited)) == [cells for row, cells in enumerate(_ORIGINAL) if row not in rows]
        kept = [line for at, line in enumerate(_lines(host)) if at not in removed_lines]
        assert [line.rstrip("\r\n") for line in _lines(edited)] == [line.rstrip("\r\n") for line in kept]
        assert _lines(edited)[:-1] == kept[:-1]

    def test_the_text_ends_in_a_line_ending_exactly_when_it_did(self, host: str) -> None:
        edited = with_rows(host, _the_table(host), removed={2})

        assert edited.endswith(("\r", "\n")) == host.endswith(("\r", "\n"))


class TestAnAddedRowFollowsTheTable:
    @pytest.mark.parametrize("text", _PERMITTED_TEXTS)
    def test_the_rows_read_back_in_order_after_the_ones_that_stood(self, host: str, text: str) -> None:
        added = [("N4", escape_cell(text), ""), ("N5", "", escape_cell(text))]

        edited = with_rows(host, _the_table(host), added=added)

        assert _plain(_the_table(edited)) == [*_ORIGINAL, ["N4", text, ""], ["N5", "", text]]

    def test_every_line_that_stood_is_the_line_it_was(self, host: str) -> None:
        table = _the_table(host)
        after_table = table.first_line + table.line_count

        edited = with_rows(host, table, added=[("N4", "new", "")])

        before, after = _lines(host), _lines(edited)
        assert [line.rstrip("\r\n") for line in after[:after_table]] == [
            line.rstrip("\r\n") for line in before[:after_table]
        ]
        assert after[: after_table - 1] == before[: after_table - 1]
        assert after[after_table + 1 :] == before[after_table:]
        assert edited.endswith(("\r", "\n")) == host.endswith(("\r", "\n"))

    def test_an_added_row_ends_as_the_tables_lines_end(self) -> None:
        host = _HOSTS["carriage-returns"]

        edited = with_rows(host, _the_table(host), added=[("N4", "new", "")])

        assert "\r\n| N4 | new | |\r\n" in edited
        assert "\n" not in edited.replace("\r\n", "")

    def test_a_table_with_no_rows_takes_its_first(self) -> None:
        host = "## Notes\n\n| Id | Note |\n|---|---|"

        edited = with_rows(host, _the_table(host), added=[("N1", "first")])

        assert edited == "## Notes\n\n| Id | Note |\n|---|---|\n| N1 | first |"


class TestEditsOfOneCallAreMadeTogether:
    def test_a_change_a_removal_and_an_addition(self, host: str) -> None:
        table = _the_table(host)

        edited = with_rows(host, table, changed={0: ("N1", "a\\|b", "")}, removed={1}, added=[("N4", "", "new")])

        assert _plain(_the_table(edited)) == [["N1", "a|b", ""], ["N3", "a|b", "done"], ["N4", "", "new"]]

    def test_the_other_tables_of_the_text_are_untouched(self) -> None:
        host = _HOSTS["between-other-tables"]

        edited = with_rows(host, _the_table(host), changed={1: ("N2", "x", "y")}, added=[("N4", "", "")])

        untouched = [table for table in tables_in(host) if table.header[0] != "Id"]
        assert [(t.header, t.rows) for t in tables_in(edited) if t.header[0] != "Id"] == [
            (t.header, t.rows) for t in untouched
        ]
        assert "```\n| not | a table |\n|---|---|\n```\n" in edited

    def test_a_cell_that_would_not_read_back_as_one_is_refused(self, host: str) -> None:
        with pytest.raises(ValueError, match="not one table cell"):
            with_rows(host, _the_table(host), changed={0: ("N1", "a|b", "")})
