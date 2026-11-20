"""An entity file's `## Properties` section: the attribute rows it states, read and written.

The section is a markdown table of two columns, so *what a row is* belongs to
`src.domain.markdown_table` and is not decided here. What this module owns is the section around it:
where it starts and ends, the placeholder row an entity without properties carries, and that a key is
plain text while a value is a cell spelled by the typed property codec
(`src.domain.ontology_representation.property_value`), which the caller decodes.

Three readers used to answer this — the index's, the editor's and the verifier's — and they disagreed
on a value carrying an escaped pipe or three hyphens, on a property named like the header, and on
whether an empty value is stated at all. The last is a question about meaning rather than syntax, so
this module answers the syntax (`key → ""`) and the verifier, which treats an empty cell as unstated,
says so itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from src.domain.markdown_table import (
    escape_cell,
    format_table,
    spans_lines,
    tables_in,
    text_lines,
    unescape_cell,
)

PROPERTIES_HEADING = "## Properties"

_HEADER = ("Attribute", "Value")

#: The cell of the placeholder row, which states nothing and is never read as a property.
_NO_PROPERTIES = "(none)"

#: What ends the section: the next heading of its own level, or a section marker comment.
_SECTION_ENDS = ("## ", "<!--")


def _section_lines(text: str) -> Iterator[str] | None:
    """The lines under the heading, up to the next section; `None` when there is no such heading."""
    lines = iter(text_lines(text))
    if not any(line.strip() == PROPERTIES_HEADING for line in lines):
        return None
    return iter(_until_next_section(lines))


def _until_next_section(lines: Iterator[str]) -> Iterator[str]:
    for line in lines:
        if line.strip().startswith(_SECTION_ENDS):
            return
        yield line


def read_properties(text: str) -> dict[str, str] | None:
    """Each attribute and its value cell as spelled, or `None` when the text has no Properties section.

    An empty value is stated as `""`. Every table in the section contributes; a later row for the same
    attribute wins, which is what three line-by-line readers each did before this was one.
    """
    section = _section_lines(text)
    if section is None:
        return None
    return {
        unescape_cell(row[0]): row[1]
        for table in tables_in("\n".join(section))
        if len(table.header) >= len(_HEADER)
        for row in table.rows
        if row[0] != _NO_PROPERTIES
    }


def format_properties_section(properties: Iterable[tuple[str, str]]) -> list[str]:
    """The section's lines, from attribute names and their already-encoded value cells.

    Refuses an attribute name that holds a line ending. A value of several lines is the codec's to
    spell and arrives here as one; a name has no such spelling, and a row is one line.
    """
    rows = [(escape_cell(_one_line(name)), cell) for name, cell in properties]
    table = format_table(_HEADER, rows or [(_NO_PROPERTIES, _NO_PROPERTIES)])
    return [PROPERTIES_HEADING, "", *text_lines(table)]


def _one_line(name: str) -> str:
    if spans_lines(name):
        raise ValueError(
            f"Attribute name {name!r} holds a line break, and an attribute name is one line. "
            "Put the text in the attribute's value, which may span lines, and give it a one-line name."
        )
    return name
