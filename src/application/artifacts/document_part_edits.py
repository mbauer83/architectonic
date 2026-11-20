"""An edit of one part of a document: a section, a text, or rows of a typed table.

Each is a value saying what to change, and a function from the document's content to its content
with that change made and **every other byte as it was** — the frontmatter, the other sections, the
line endings, and whether the file ends in one. A caller that changes three sentences of a long
document sends three sentences, and a reviewer of the commit sees three sentences change.

Nothing here reads a syntax of its own. What a heading is and what it holds is
`src.application.artifacts.document_sections`'s; a table and its rows are edited by
`src.application.artifacts.document_table_edits`, over the one reading of them.

**An edit that cannot be made as stated is refused, with a sentence naming the fix.** Nothing is
guessed: a heading path that names two headings, a text that occurs another number of times than the
caller expected, and a row that changed since the caller read it are each the caller's to resolve.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from src.application.artifacts.document_sections import HeadingSpan, document_body, document_headings
from src.domain.markdown_table import text_lines
from src.domain.ontology_representation.property_value import PropertyValue

#: What a cell is stated as: the typed value of its column, or nothing for an empty cell.
CellValue = PropertyValue | None


class DocumentEditRefused(ValueError):
    """The edit cannot be made as stated. The message says what to change."""


class RowChangedSinceRead(DocumentEditRefused):
    """A row is not what the edit says it was based on: another writer changed it first."""


@dataclass(frozen=True)
class SectionReplacement:
    """Replace what stands under one heading, the headings beneath it included."""

    heading_path: tuple[str, ...]
    text: str

    def with_text(self, rewritten: Callable[[str], str]) -> SectionReplacement:
        return replace(self, text=rewritten(self.text))


@dataclass(frozen=True)
class TextReplacement:
    """Replace an exact text, wherever in the body it occurs, the stated number of times."""

    find: str
    replacement: str
    expected_matches: int = 1

    def with_text(self, rewritten: Callable[[str], str]) -> TextReplacement:
        return replace(self, replacement=rewritten(self.replacement))


@dataclass(frozen=True)
class RowAddition:
    """A new row. Its id is the table's next; `cells` are its values by column name."""

    cells: Mapping[str, CellValue]


@dataclass(frozen=True)
class RowChange:
    """New values for some cells of one row. `based_on` is the row as the caller read it."""

    row_id: str
    based_on: Mapping[str, CellValue]
    cells: Mapping[str, CellValue]


@dataclass(frozen=True)
class RowRemoval:
    row_id: str
    based_on: Mapping[str, CellValue]


RowEdit = RowAddition | RowChange | RowRemoval


@dataclass(frozen=True)
class TableRowEdits:
    """Rows of one declared table added, changed and removed together."""

    table: str
    edits: tuple[RowEdit, ...]


PartEdit = SectionReplacement | TextReplacement | TableRowEdits


def _spliced(content: str, edit_body: Callable[[str], str]) -> str:
    """`content` with its body edited and its frontmatter block as it was."""
    body = document_body(content)
    return content[: len(content) - len(body)] + edit_body(body)


def _shown(path: tuple[str, ...]) -> str:
    return " > ".join(path)


def _addressed(body: str, heading_path: tuple[str, ...]) -> HeadingSpan:
    headings = document_headings(body)
    named = [heading for heading in headings if heading.path == heading_path]
    if len(named) == 1:
        return named[0]
    if named:
        raise DocumentEditRefused(
            f"{len(named)} headings of this document are '{_shown(heading_path)}'; a section edit "
            "addresses one. Rename one of them, or replace the whole body."
        )
    siblings = [_shown(heading.path) for heading in headings if heading.path[:-1] == heading_path[:-1]]
    raise DocumentEditRefused(
        f"This document has no heading '{_shown(heading_path)}'. "
        + (f"At that level it has: {', '.join(siblings)}." if siblings else "It has no heading at that level.")
    )


_LINE_BREAKS = ("\r", "\n")


def _line_ending_of(body: str) -> str:
    """The line ending `body` uses, read off its first; a line feed where it has none."""
    first_break = min((at for at in (body.find("\r"), body.find("\n")) if at >= 0), default=len(body))
    return "\r\n" if body.startswith("\r\n", first_break) else body[first_break : first_break + 1] or "\n"


def _first_line_ending(text: str) -> str:
    return "\r\n" if text.startswith("\r\n") else text[:1] if text.startswith(_LINE_BREAKS) else ""


def _closing_of(body: str, heading: HeadingSpan, newline: str) -> tuple[str, str]:
    """How the text under `heading` ends, and what separates it from what follows.

    The ending of its last line, then the blank lines after that — which are not the section's text,
    and so are what a replacement leaves standing.
    """
    held = body[heading.content_start : heading.end]
    is_last = heading.end == len(body)
    if held.strip():
        after_text = held[len(held.rstrip()) :]
        ending = _first_line_ending(after_text)
        return ending or ("" if is_last else newline), after_text[len(ending) :]
    if is_last:
        return (newline if body.endswith(_LINE_BREAKS) else ""), ""
    return newline, newline


def _replaced_section(body: str, edit: SectionReplacement) -> str:
    if not edit.heading_path:
        raise DocumentEditRefused("A section edit names the heading it replaces, as the path of titles down to it.")
    heading = _addressed(body, edit.heading_path)
    stated = edit.text.lstrip("\r\n").rstrip()
    if any(inner.level <= heading.level for inner in document_headings(stated)):
        raise DocumentEditRefused(
            f"The text for '{_shown(edit.heading_path)}' holds a heading at that section's level or above, which "
            "would end the section and begin another. Send the text under the heading only; a heading "
            f"beneath it has at least {heading.level + 1} hashes."
        )
    newline = _line_ending_of(body)
    closing, separation = _closing_of(body, heading, newline)
    before = body[: heading.content_start]
    if not stated:
        return before + (separation if heading.end < len(body) else "") + body[heading.end :]
    opening = "" if before.endswith(_LINE_BREAKS) else newline
    text = newline.join(text_lines(stated))
    return f"{before}{opening}{newline}{text}{closing}{separation}{body[heading.end:]}"


def _replaced_text(body: str, edit: TextReplacement) -> str:
    if not edit.find:
        raise DocumentEditRefused("A replacement names the text to find; an empty text occurs everywhere.")
    found = body.count(edit.find)
    if found != edit.expected_matches:
        raise DocumentEditRefused(
            f"The text occurs {found} time{'' if found == 1 else 's'} in this document's body and the edit "
            f"expects {edit.expected_matches}. "
            + (
                "Read the document again: it does not hold that text as written."
                if not found
                else "Give more of the surrounding text to name one occurrence, or state the number expected."
            )
        )
    return body.replace(edit.find, edit.replacement)


def replace_section(content: str, edit: SectionReplacement) -> str:
    """`content` with the text under one heading replaced, and every other byte as it was."""
    return _spliced(content, lambda body: _replaced_section(body, edit))


def replace_text(content: str, edit: TextReplacement) -> str:
    """`content` with an exact text of its body replaced, where it occurs as often as expected."""
    return _spliced(content, lambda body: _replaced_text(body, edit))
