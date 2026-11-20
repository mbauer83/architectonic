"""A markdown table has one writer and one reader, and they agree over what the syntax permits.

Stated over the syntax and not over what the product writes today: the shipped writers happen never to
put a pipe, a backslash or three hyphens in a cell, and a round trip asserted only over their output
passed against three readers that could not read any of those back.
"""

from __future__ import annotations

import pytest

from src.domain.markdown_table import (
    Alignment,
    MarkdownTable,
    escape_cell,
    format_row,
    format_table,
    row_cells,
    tables_in,
    unescape_cell,
)

#: Plain texts a cell may have to carry. Each is something a line-by-line `split("|")` reading, or a
#: reading that takes any line holding `---` for the delimiter row, gets wrong.
_PERMITTED_TEXTS = (
    "plain",
    "",
    "a|b",
    "ends in a pipe|",
    "|",
    "back\\slash",
    "ends in a backslash\\",
    "a backslash then a pipe \\|",
    "\\\\|\\|",
    "source---target",
    "---",
    ":--",
    "`code | span`",
    "[a link|with a pipe](target.md)",
    "ünïcödé ✓",
    "&nbsp;",
)

_ALIGNMENTS: tuple[Alignment, ...] = ("", "left", "right", "center")


def _read_back(header: list[str], rows: list[list[str]], alignment: tuple[Alignment, ...] = ()) -> MarkdownTable:
    (table,) = tables_in(format_table(header, rows, alignment))
    return table


class TestWhatIsWrittenReadsBack:
    @pytest.mark.parametrize("text", _PERMITTED_TEXTS)
    def test_a_cell_reads_back_as_the_text_it_was_written_from(self, text: str) -> None:
        table = _read_back(["Attribute", "Value"], [["before", escape_cell(text)], [escape_cell(text), "after"]])

        assert [[unescape_cell(cell) for cell in row] for row in table.rows] == [["before", text], [text, "after"]]

    @pytest.mark.parametrize("text", _PERMITTED_TEXTS)
    def test_a_header_cell_reads_back_too(self, text: str) -> None:
        table = _read_back([escape_cell(text), "Value"], [["a", "b"]])

        assert unescape_cell(table.header[0]) == text
        assert table.rows == (("a", "b"),)

    def test_every_alignment_reads_back(self) -> None:
        table = _read_back(["a", "b", "c", "d"], [["1", "2", "3", "4"]], _ALIGNMENTS)

        assert table.alignment == _ALIGNMENTS

    def test_a_table_without_rows_reads_back(self) -> None:
        assert _read_back(["", "A", "B"], []) == MarkdownTable(header=("", "A", "B"), alignment=("", "", ""), rows=())

    def test_a_written_table_is_rewritten_identically(self) -> None:
        rows = [["**r**", "✓", "&nbsp;"], ["**s**", "", "a\\|b"]]
        written = format_table(["", "A", "B"], rows, ("", "left", "center"))
        (table,) = tables_in(written)

        assert format_table(table.header, table.rows, table.alignment) == written

    def test_the_spelling_is_the_one_stored_files_carry(self) -> None:
        assert format_table(["Attribute", "Value"], [["owner", "team"], ["tier", ""]]).splitlines() == [
            "| Attribute | Value |",
            "|---|---|",
            "| owner | team |",
            "| tier | |",
        ]

    @pytest.mark.parametrize("cell", ["a|b", "ends in a pipe |", "two\nlines", "carriage\rreturn"])
    def test_a_cell_that_would_not_read_back_as_one_is_refused(self, cell: str) -> None:
        with pytest.raises(ValueError, match="escape_cell"):
            format_row(["key", cell])


class TestWhatTheSyntaxPermitsIsRead:
    def test_outer_pipes_are_optional(self) -> None:
        (table,) = tables_in("a | b\n--- | ---\n1 | 2\n| 3 | 4\n5 | 6 |")

        assert table.header == ("a", "b")
        assert table.rows == (("1", "2"), ("3", "4"), ("5", "6"))

    def test_a_delimiter_row_may_be_spaced_and_carry_colons(self) -> None:
        (table,) = tables_in("| a | b | c | d |\n| :--- | ---: | :---: | - |\n| 1 | 2 | 3 | 4 |")

        assert table.alignment == ("left", "right", "center", "")

    def test_line_endings_and_trailing_whitespace_do_not_matter(self) -> None:
        plain = tables_in("| a | b |\n|---|---|\n| 1 | 2 |")
        noisy = tables_in("| a | b |  \r\n|---|---|\t\r\n| 1 | 2 | \r\n")

        assert noisy == plain

    def test_a_table_may_follow_a_paragraph_directly(self) -> None:
        (table,) = tables_in("Some prose.\n| a | b |\n|---|---|\n| 1 | 2 |\n\nMore prose.")

        assert table.first_line == 1
        assert table.cell_lines == (1, 3)
        assert table.rows == (("1", "2"),)

    def test_a_row_is_as_wide_as_its_header(self) -> None:
        (table,) = tables_in("| a | b |\n|---|---|\n| only |\n| 1 | 2 | beyond |\n| | |")

        assert table.rows == (("only", ""), ("1", "2"), ("", ""))

    def test_a_code_span_does_not_protect_a_pipe(self) -> None:
        assert row_cells("| `a|b` | c |") == ("`a", "b`", "c")
        assert row_cells("| `a\\|b` | c |") == ("`a\\|b`", "c")

    def test_an_escaped_backslash_does_not_escape_the_pipe_after_it(self) -> None:
        assert row_cells("| a\\\\| b |") == ("a\\\\", "b")

    def test_a_heading_or_a_section_marker_ends_a_table(self) -> None:
        first, second = tables_in("| a |\n|---|\n| 1 |\n## Next\n| b |\n|---|\n| 2 |\n<!-- §display -->\n| 3 |")

        assert (first.rows, second.rows) == ((("1",),), (("2",),))

    @pytest.mark.parametrize(
        "not_a_table",
        [
            pytest.param("---\nname: a | b\n---\n", id="frontmatter-fence"),
            pytest.param("Heading | like\n---\n", id="setext-rule"),
            pytest.param("| a | b |\n| 1 | 2 |\n", id="no-delimiter-row"),
            pytest.param("| a | b |\n|---|\n| 1 | 2 |\n", id="delimiter-of-another-width"),
            pytest.param("```\n| a | b |\n|---|---|\n| 1 | 2 |\n```\n", id="inside-a-code-fence"),
            pytest.param("    | a | b |\n    |---|---|\n", id="indented-code"),
            pytest.param("| a | b |\n|-x-|---|\n", id="delimiter-with-other-characters"),
        ],
    )
    def test_what_is_not_a_table_is_not_read_as_one(self, not_a_table: str) -> None:
        assert tables_in(not_a_table) == ()
