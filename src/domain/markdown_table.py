"""A markdown table: where one is in a text, the cells it holds, and how one is written.

The one reading and the one writing of the GitHub-flavoured table this project stores in its own
files — an entity's `## Properties`, a matrix diagram's body, the generated tool tables.

**What is a table.** A header row, then a delimiter row with one cell per header cell, each of hyphens
with an optional colon at either end, then body rows up to the first blank line or the start of
another block. A delimiter row carries at least one pipe: a bare `---` is a frontmatter fence or a
rule, and a reading that took it for a one-column delimiter would find a table in every file's
frontmatter. Lines inside a code fence are not read.

**What is a cell.** The text between two pipes that no backslash escapes, trimmed. One leading and
one trailing pipe are optional. A backslash escapes the character after it, so `\\|` is a pipe inside
a cell and `\\\\|` is a backslash and then the end of the cell. Code spans do not protect a pipe —
GFM says so, and a reading that let them would disagree with every renderer about where a cell ends.
A body row is as wide as its header: missing cells read empty, cells past the last column are not
read.

**Cells are held as spelled.** `MarkdownTable` keeps each cell's escapes, because the typed property
codec (`src.domain.ontology_representation.property_value`) layers its own line-break escape over
this one and can only undo both in a single pass. A caller holding plain text converts with
`escape_cell` and `unescape_cell`; `format_row` refuses a cell that would not read back as one cell,
which is what keeps the pair a round trip.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

Alignment = Literal["", "left", "right", "center"]

_PIPE = "|"
_ESCAPE = "\\"

#: How each alignment is spelled in a delimiter cell, in the three-character form this project writes.
_DELIMITER_CELL: dict[Alignment, str] = {"": "---", "left": ":--", "right": "--:", "center": ":-:"}

#: What opens a block that ends a table without a blank line between: a heading, a block quote, a code
#: fence, or raw HTML — which is where this project's own `<!-- §section -->` markers fall.
_BLOCK_OPENERS = ("#", ">", "```", "~~~", "<")

_FENCES = ("```", "~~~")

#: Four columns of indentation make a line code rather than a table row.
_CODE_INDENT = 4


@dataclass(frozen=True)
class MarkdownTable:
    """One table: its cells as spelled, and where it sits in the text it was read from."""

    header: tuple[str, ...]
    alignment: tuple[Alignment, ...]
    rows: tuple[tuple[str, ...], ...]
    #: Index of the header line among the text's lines. Zero for a table that was not read from one.
    first_line: int = 0

    @property
    def cell_lines(self) -> tuple[int, ...]:
        """The lines that carry cells — the header and each body row, not the delimiter."""
        body_start = self.first_line + 2
        return (self.first_line, *range(body_start, body_start + len(self.rows)))

    @property
    def line_count(self) -> int:
        return 2 + len(self.rows)


def _boundaries(line: str) -> Iterator[int]:
    """Positions of the pipes no backslash escapes."""
    position = 0
    while position < len(line):
        if line[position] == _ESCAPE:
            position += 2
            continue
        if line[position] == _PIPE:
            yield position
        position += 1


def row_cells(line: str) -> tuple[str, ...]:
    """The cells of one row line, as spelled and trimmed. A line without a pipe is one cell."""
    text = line.strip()
    boundaries = list(_boundaries(text))
    if boundaries and boundaries[0] == 0:
        text, boundaries = text[1:], [at - 1 for at in boundaries[1:]]
    if boundaries and boundaries[-1] == len(text) - 1:
        text, boundaries = text[:-1], boundaries[:-1]
    starts = [0, *(at + 1 for at in boundaries)]
    ends = [*boundaries, len(text)]
    return tuple(text[start:end].strip() for start, end in zip(starts, ends, strict=True))


def _alignment_of(cell: str) -> Alignment | None:
    """What a delimiter cell says, or `None` when the cell is not one."""
    left, right = cell.startswith(":"), cell.endswith(":") and len(cell) > 1
    hyphens = cell[1 if left else 0 : len(cell) - (1 if right else 0)]
    if not hyphens or hyphens.strip("-"):
        return None
    match (left, right):
        case (True, True):
            return "center"
        case (True, False):
            return "left"
        case (False, True):
            return "right"
        case _:
            return ""


def _delimiter_alignment(line: str) -> tuple[Alignment, ...] | None:
    """The alignments a delimiter row states, or `None` when the line is not a delimiter row."""
    if next(_boundaries(line), None) is None:
        return None
    stated = [_alignment_of(cell) for cell in row_cells(line)]
    alignments = tuple(alignment for alignment in stated if alignment is not None)
    return alignments if len(alignments) == len(stated) else None


def _indentation(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _ends_table(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith(_BLOCK_OPENERS)


def _fitted[Cell: str](cells: tuple[Cell, ...], width: int, empty: Cell) -> tuple[Cell, ...]:
    """`cells` at exactly `width`: cut where there are more, filled with `empty` where there are fewer."""
    return (*cells[:width], *(empty for _ in range(width - len(cells))))


def _table_at(lines: Sequence[str], at: int) -> MarkdownTable | None:
    """The table whose header is line `at`, or `None` when no table starts there."""
    if at + 1 >= len(lines) or _ends_table(lines[at]) or _indentation(lines[at]) >= _CODE_INDENT:
        return None
    alignment = _delimiter_alignment(lines[at + 1])
    header = row_cells(lines[at])
    if alignment is None or len(alignment) != len(header):
        return None
    body: list[tuple[str, ...]] = []
    for line in lines[at + 2 :]:
        if _ends_table(line):
            break
        body.append(_fitted(row_cells(line), len(header), ""))
    return MarkdownTable(header=header, alignment=alignment, rows=tuple(body), first_line=at)


def tables_in(text: str) -> tuple[MarkdownTable, ...]:
    """Every table in `text`, in order. Line endings and trailing whitespace do not matter."""
    lines = text.splitlines()
    found: list[MarkdownTable] = []
    fence: str | None = None
    at = 0
    while at < len(lines):
        opener = lines[at].strip()[:3]
        if fence is not None:
            fence = None if opener == fence else fence
            at += 1
            continue
        if opener in _FENCES:
            fence = opener
            at += 1
            continue
        table = _table_at(lines, at)
        found.extend([table] if table else [])
        at += table.line_count if table else 1
    return tuple(found)


def escape_cell(text: str) -> str:
    """Spell plain text so that it reads back as one cell: escape the backslash, then the pipe."""
    return text.replace(_ESCAPE, _ESCAPE * 2).replace(_PIPE, _ESCAPE + _PIPE)


def unescape_cell(cell: str) -> str:
    """The plain text a spelled cell stands for. Only the two escapes `escape_cell` writes are undone."""
    out: list[str] = []
    position = 0
    while position < len(cell):
        escaped = cell[position + 1 : position + 2] if cell[position] == _ESCAPE else ""
        if escaped in (_ESCAPE, _PIPE) and escaped:
            out.append(escaped)
            position += 2
            continue
        out.append(cell[position])
        position += 1
    return "".join(out)


def format_row(cells: Iterable[str]) -> str:
    """One row line from spelled cells. An empty cell is written as a single space between pipes."""
    spelled = tuple(cell.strip() for cell in cells)
    for cell in spelled:
        if row_cells(f"{_PIPE} {cell} {_PIPE}") != (cell,) or len(cell.splitlines()) > 1:
            raise ValueError(f"not one table cell as spelled — escape it with escape_cell first: {cell!r}")
    return _PIPE + "".join(f" {cell} {_PIPE}" if cell else f" {_PIPE}" for cell in spelled)


def format_table(
    header: Sequence[str],
    rows: Iterable[Sequence[str]],
    alignment: Sequence[Alignment] = (),
) -> str:
    """The table as this project writes one: a header, a compact delimiter row, one line per row."""
    unaligned: Alignment = ""
    aligned = _fitted(tuple(alignment), len(header), unaligned)
    delimiter = _PIPE + "".join(_DELIMITER_CELL[stated] + _PIPE for stated in aligned)
    return "\n".join([format_row(header), delimiter, *(format_row(row) for row in rows)])
