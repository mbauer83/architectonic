"""The attribute lines a reading prints, broken so a laid-out element keeps the width it is stored at.

A stored layout states where each element is and, only where an author resized it, how big. A reading
lens appends attribute lines to an element's label before PlantUML draws it, and a long value then
draws the element wider than the picture the layout was made over — over its neighbour, with its box
pushed over the next. So the lines are broken instead, and the element grows downward in its column.

Where to break is measured, never estimated: PlantUML has already drawn the lensed picture once, and
its picture says how wide each printed word is and how much room the element keeps either side of its
text. The stored picture says how wide the element is meant to be. Nothing moves a neighbour.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from src.domain.diagrams.layout.rendered_picture import DrawnElement, MeasuredWord, RenderedPicture
from src.infrastructure.rendering.layout.plantuml_svg_reader import read_rendered_picture

#: How far a width may exceed the stored one and still be the same width.
_SAME_WIDTH = 0.5

#: A row is a line of the label: its words share a baseline.
_SAME_BASELINE = 0.5

Wrapping = Callable[[str, tuple[str, ...]], tuple[str, ...]]


def _rows(words: Sequence[MeasuredWord]) -> list[list[MeasuredWord]]:
    rows: list[list[MeasuredWord]] = []
    for word in words:
        if rows and abs(rows[-1][0].start.y - word.start.y) <= _SAME_BASELINE:
            rows[-1].append(word)
        else:
            rows.append([word])
    return rows


def _span(row: Sequence[MeasuredWord]) -> float:
    return row[-1].start.x + row[-1].width - row[0].start.x


def _space(rows: Sequence[Sequence[MeasuredWord]]) -> float:
    """The width PlantUML set between two words of a printed line."""
    gaps = [after.start.x - (before.start.x + before.width) for row in rows for before, after in zip(row, row[1:])]
    return min(gaps, default=0.0)


def _broken(line: str, widths: Sequence[float], room: float, space: float) -> list[str]:
    """*line* broken between words into lines no wider than *room*; a word wider than it stands alone."""
    lines: list[list[str]] = []
    used = 0.0
    for word, width in zip(line.split(), widths, strict=True):
        needed = width + (space if lines and lines[-1] else 0.0)
        if lines and lines[-1] and used + needed > room:
            lines.append([])
            used, needed = 0.0, width
        if not lines:
            lines.append([])
        lines[-1].append(word)
        used += needed
    return [" ".join(words) for words in lines]


def _held(element: DrawnElement, stored_width: float, lines: tuple[str, ...]) -> tuple[str, ...]:
    """*lines*, the last rows of *element*'s label, broken to fit *stored_width*; as they were where unread."""
    if element.extent.width <= stored_width + _SAME_WIDTH:
        return lines
    # The printed words are the label's last ones, in order — PlantUML may already have broken a long
    # line at its own wrap width, so they are matched word by word rather than row by row.
    texts = [line.split() for line in lines]
    count = sum(len(words) for words in texts)
    printed = list(element.words[len(element.words) - count:]) if 0 < count < len(element.words) else []
    if [word.text for word in printed] != [text for words in texts for text in words]:
        return lines
    rows = _rows(element.words)
    room = stored_width - (element.extent.width - max(_span(row) for row in rows))
    space = _space(_rows(printed))
    held: list[str] = []
    for line, words in zip(lines, texts, strict=True):
        widths, printed = [word.width for word in printed[: len(words)]], printed[len(words):]
        held.extend(_broken(line, widths, room, space))
    return tuple(held)


def printed_lines_held(lensed_svg: str, stored_svg: str) -> Wrapping | None:
    """How to break each element's printed lines so it is drawn no wider than in *stored_svg*.

    *lensed_svg* is PlantUML's picture of the lensed body, before any layout composes it. None when
    either picture cannot be read, or no element is drawn wider than it is stored.
    """
    lensed, stored = read_rendered_picture(lensed_svg), read_rendered_picture(stored_svg)
    if not isinstance(lensed, RenderedPicture) or not isinstance(stored, RenderedPicture):
        return None
    widths: Mapping[str, float] = {
        alias: stored.elements[alias].extent.width
        for alias, element in lensed.elements.items()
        if alias in stored.elements and element.extent.width > stored.elements[alias].extent.width + _SAME_WIDTH
    }
    if not widths:
        return None

    def wrapped(alias: str, lines: tuple[str, ...]) -> tuple[str, ...]:
        width = widths.get(alias)
        return lines if width is None else _held(lensed.elements[alias], width, lines)

    return wrapped
