"""A section or a text of a document is replaced, and every other byte of it stays.

Stated over documents an author may have written rather than ones the write path emits: frontmatter
with a comment and quoting of its own, sections that share a title at different depths, a section
with nothing under it, a last section with and without a final line ending, carriage returns.
"""

from __future__ import annotations

import pytest

from src.application.artifacts.document_part_edits import (
    DocumentEditRefused,
    SectionReplacement,
    TextReplacement,
    replace_section,
    replace_text,
)
from src.application.artifacts.document_sections import document_headings, document_section_spans

_FRONTMATTER = '---\n# kept as written\ntitle:   "Checkout under stress"\nartifact-id: ADR@1.a.b\nstatus: draft\n---\n'

_DOCUMENT = (
    _FRONTMATTER
    + "\nA line before any section.\n\n"
    + "## Context\n\nThe provider is called inline.\n\n### Notes\n\nFirst note.\n\n"
    + "## Decision\n## Consequences\n\n- one\n- two\n\n### Notes\n\nSecond note.\n\n\n"
    + "## Status\n\nOpen.\n"
)


def _section(path: tuple[str, ...], text: str, document: str = _DOCUMENT) -> str:
    return replace_section(document, SectionReplacement(path, text))


def _around(document: str, heading_line: str, following: str | None) -> tuple[str, str]:
    """What stands up to and including a heading line, and from the next heading on."""
    upto = document.index(heading_line) + len(heading_line)
    return document[:upto], ("" if following is None else document[document.index(following, upto) :])


class TestASectionIsReplaced:
    def test_the_text_under_the_heading_is_the_new_text_and_the_rest_is_byte_identical(self) -> None:
        before, after = _around(_DOCUMENT, "## Context\n", "## Decision")

        edited = _section(("Context",), "Queued instead.\n\n### Notes\n\nRewritten.")

        assert edited == before + "\nQueued instead.\n\n### Notes\n\nRewritten.\n\n" + after

    def test_a_heading_beneath_a_section_is_addressed_by_its_path(self) -> None:
        before, after = _around(_DOCUMENT, "- two\n\n### Notes\n", "## Status")

        edited = _section(("Consequences", "Notes"), "Third note.")

        assert edited == before + "\nThird note.\n\n\n" + after

    def test_a_section_with_nothing_under_it_takes_text_and_a_blank_line_before_the_next(self) -> None:
        before, after = _around(_DOCUMENT, "## Decision\n", "## Consequences")

        assert _section(("Decision",), "Queue the payment.") == before + "\nQueue the payment.\n\n" + after

    @pytest.mark.parametrize("ending", ["\n", "", "\n\n"])
    def test_the_last_section_ends_the_file_as_it_did(self, ending: str) -> None:
        document = _DOCUMENT.rstrip("\n") + ending
        before, _ = _around(document, "## Status" + ("\n" if "## Status\n" in document else ""), None)

        edited = _section(("Status",), "Closed.", document)

        assert edited == document[: document.index("## Status")] + "## Status\n\nClosed." + ending
        assert edited.startswith(before)

    def test_a_heading_that_ends_the_file_without_a_line_ending_takes_text(self) -> None:
        document = _FRONTMATTER + "\n## Context\n\ntext\n\n## Status"

        assert _section(("Status",), "Closed.", document) == document + "\n\nClosed."

    def test_a_document_of_carriage_returns_keeps_them(self) -> None:
        document = _DOCUMENT.replace("\n", "\r\n")

        edited = _section(("Context",), "Queued instead.\nOn two lines.", document)

        before, after = _around(document, "## Context\r\n", "## Decision")
        assert edited == before + "\r\nQueued instead.\r\nOn two lines.\r\n\r\n" + after

    def test_an_emptied_section_keeps_its_heading_and_its_distance_to_the_next(self) -> None:
        before, after = _around(_DOCUMENT, "## Context\n", "## Decision")

        assert _section(("Context",), "") == before + "\n" + after

    def test_the_sections_read_back_as_the_edit_left_them(self) -> None:
        edited = _section(("Context",), "Queued instead.")

        untouched = {name: text for name, text in document_section_spans(_DOCUMENT).items() if name != "Context"}
        read = document_section_spans(edited)
        assert read["Context"] == "## Context\n\nQueued instead.\n\n"
        assert {name: text for name, text in read.items() if name != "Context"} == untouched
        assert [heading.path for heading in document_headings(edited)] == [
            ("Context",), ("Decision",), ("Consequences",), ("Consequences", "Notes"), ("Status",)
        ]


class TestASectionEditThatCannotBeMadeIsRefused:
    def test_a_heading_the_document_does_not_have(self) -> None:
        with pytest.raises(DocumentEditRefused, match="no heading 'Rationale'. At that level it has: Context, Deci"):
            _section(("Rationale",), "x")

    def test_a_heading_beneath_the_wrong_section(self) -> None:
        with pytest.raises(DocumentEditRefused, match="no heading 'Decision > Notes'. It has no heading at that level"):
            _section(("Decision", "Notes"), "x")

    def test_a_path_two_headings_share(self) -> None:
        document = _DOCUMENT + "\n## Status\n\nAgain.\n"

        with pytest.raises(DocumentEditRefused, match="2 headings of this document are 'Status'"):
            _section(("Status",), "x", document)

    def test_a_text_that_would_begin_another_section(self) -> None:
        with pytest.raises(DocumentEditRefused, match="holds a heading at that section's level or above"):
            _section(("Context",), "Queued.\n\n## Smuggled\n\ntext")

    def test_a_text_holding_a_heading_beneath_the_section_is_taken(self) -> None:
        assert "### Deeper\n" in _section(("Context",), "### Deeper\n\ntext")

    def test_no_path(self) -> None:
        with pytest.raises(DocumentEditRefused, match="names the heading it replaces"):
            _section((), "x")


class TestATextIsReplaced:
    def test_the_one_occurrence_is_replaced_and_the_rest_is_byte_identical(self) -> None:
        edited = replace_text(_DOCUMENT, TextReplacement("called inline", "queued"))

        assert edited == _DOCUMENT.replace("called inline", "queued")
        assert len(edited) == len(_DOCUMENT) - len("called inline") + len("queued")

    def test_a_text_spanning_lines_is_found(self) -> None:
        edited = replace_text(_DOCUMENT, TextReplacement("- one\n- two", "- three"))

        assert "\n\n- three\n\n### Notes" in edited

    def test_every_occurrence_is_replaced_when_that_many_are_expected(self) -> None:
        edited = replace_text(_DOCUMENT, TextReplacement("### Notes", "### Remarks", expected_matches=2))

        assert edited.count("### Remarks") == 2 and "### Notes" not in edited

    def test_the_frontmatter_is_not_searched(self) -> None:
        with pytest.raises(DocumentEditRefused, match="occurs 0 times"):
            replace_text(_DOCUMENT, TextReplacement("Checkout under stress", "x"))

    @pytest.mark.parametrize(
        ("find", "expected", "said"),
        [
            ("### Notes", 1, "occurs 2 times in this document's body and the edit expects 1. Give more"),
            ("The provider", 2, "occurs 1 time in this document's body and the edit expects 2"),
            ("not there", 1, "occurs 0 times in this document's body and the edit expects 1. Read the document"),
        ],
    )
    def test_another_number_of_occurrences_than_expected_is_refused(self, find: str, expected: int, said: str) -> None:
        with pytest.raises(DocumentEditRefused, match=said):
            replace_text(_DOCUMENT, TextReplacement(find, "x", expected_matches=expected))

    def test_an_empty_text_to_find_is_refused(self) -> None:
        with pytest.raises(DocumentEditRefused, match="names the text to find"):
            replace_text(_DOCUMENT, TextReplacement("", "x"))
