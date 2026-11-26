"""An element or a box drawn where a layout puts it, from the drawing PlantUML made of it.

Three cases, and in none of them is a notation drawn a second time:

* an element **moved** is its own drawing, shifted;
* a **box** is its outline stretched to its new rectangle — corners as they were drawn — with its
  title and glyph carried along, centred over it;
* an element **resized** is its own outline stretched the same way, its glyph carried, and its label
  set again line by line from the widths PlantUML measured for each word. No font is consulted: a
  word is as wide as the renderer said it was.

Every group keeps the attributes it had, so whatever identifies a shape on a rendered picture —
`plantuml_svg_reader` reads it, and the viewer's element map does — identifies it here unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from xml.etree.ElementTree import Element

from src.domain.diagrams.layout.geometry import Extent
from src.infrastructure.rendering.layout._svg_drawing import numbers_of, tag_of
from src.infrastructure.rendering.layout.svg_markup import Motion, drawn_extent, fitted, moved

#: The least room kept between a label and the side of its element.
_LEAST_PADDING = 4.0

#: Where a line's baseline sits below the top of the room the line is given, as a share of that room.
_BASELINE_SHARE = 0.78

#: A line's height as a share of its font size, where one line gives no second baseline to measure from.
_LINE_HEIGHT_SHARE = 1.165

#: A space's width as a share of the font size, where the renderer set none to measure.
_SPACE_SHARE = 0.32

_DEFAULT_FONT_SIZE = 12.0
_OPENS_A_KEPT_LINE = "«"


def _like(group: Element) -> Element:
    return Element(group.tag, dict(group.attrib))


def placed_shape(group: Element, drawn: Extent, to: Extent) -> Element:
    """The drawing in *group*, shifted from where it was *drawn* to where *to* begins."""
    return moved(group, Motion.shift(to.left - drawn.left, to.top - drawn.top))


def fitted_box(group: Element, drawn: Extent, to: Extent) -> Element:
    """A box's drawing with its outline stretched to *to* and its title and glyph centred over it."""
    outline, *heading = list(group)
    carried = Motion.shift(to.centre.x - drawn.centre.x, to.top - drawn.top)
    box = _like(group)
    box.append(fitted(outline, drawn, to))
    box.extend(moved(part, carried) for part in heading)
    return box


@dataclass(frozen=True)
class _Word:
    text: Element
    x: float
    baseline: float
    width: float


def _says_something(text: Element) -> bool:
    return bool((text.text or "").strip("  \t\n"))


def _words(texts: Sequence[Element]) -> list[_Word]:
    return [_Word(text, *numbers_of(text, "x", "y", "textLength")) for text in texts if _says_something(text)]


def _lines(words: Sequence[_Word]) -> list[list[_Word]]:
    """The words as the renderer set them, a line per baseline."""
    lines: list[list[_Word]] = []
    for word in words:
        if lines and lines[-1][0].baseline == word.baseline:
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


def _paragraphs(lines: Sequence[Sequence[_Word]]) -> list[list[_Word]]:
    """What may be wrapped together: a line opening with a guillemet — a type or specialization — stays its own."""
    paragraphs: list[list[_Word]] = []
    joins_previous = False
    for line in lines:
        kept_apart = (line[0].text.text or "").startswith(_OPENS_A_KEPT_LINE)
        if paragraphs and joins_previous and not kept_apart:
            paragraphs[-1].extend(line)
        else:
            paragraphs.append(list(line))
        joins_previous = not kept_apart
    return paragraphs


def _wrapped(paragraphs: Sequence[Sequence[_Word]], room: float, space: float, taken_first: float) -> list[list[_Word]]:
    """Each paragraph broken into lines no wider than *room*; the first line gives *taken_first* to the glyph."""
    wrapped: list[list[_Word]] = []
    for paragraph in paragraphs:
        line: list[_Word] = []
        used = 0.0
        for word in paragraph:
            budget = room - (taken_first if not wrapped else 0.0)
            needed = word.width + (space if line else 0.0)
            if line and used + needed > budget:
                wrapped.append(line)
                line, used, needed = [], 0.0, word.width
            line.append(word)
            used += needed
        if line:
            wrapped.append(line)
    return wrapped


def _font_size(text: Element) -> float:
    try:
        return float(text.get("font-size") or _DEFAULT_FONT_SIZE)
    except ValueError:
        return _DEFAULT_FONT_SIZE


def _set_again(word: _Word, x: float, baseline: float) -> Element:
    return moved(word.text, Motion.shift(x - word.x, baseline - word.baseline))


@dataclass(frozen=True)
class _Label:
    """An element's label as the renderer set it: its words by line, and the room round them."""

    marks: list[Element]
    lines: list[list[_Word]]
    space: float
    line_height: float
    #: What leads the first line before its first word: the element's glyph.
    leading: list[Element]
    glyph_left: float
    glyph_room: float
    padding: float


def _label(group: Element, drawn: Extent) -> _Label | None:
    """The label of the element drawn in *group* at *drawn*; None where it says nothing."""
    _outline, *rest = list(group)
    texts = [part for part in rest if tag_of(part) == "text"]
    marks = [part for part in rest if tag_of(part) != "text"]
    words = _words(texts)
    if not words:
        return None
    lines = _lines(words)
    first = lines[0][0]
    size = _font_size(first.text)
    blank = next((text for text in texts if not _says_something(text) and text.get("textLength")), None)
    space = float(blank.get("textLength") or 0.0) if blank is not None else size * _SPACE_SHARE
    line_height = (
        (lines[-1][0].baseline - first.baseline) / (len(lines) - 1) if len(lines) > 1 else size * _LINE_HEIGHT_SHARE
    )
    # What sits on the first line before its first word is the glyph: it leads that line wherever it goes.
    leading = [
        mark for mark in marks
        if (extent := drawn_extent(mark)) is not None and extent.right <= first.x + 1.0
        and extent.top <= first.baseline <= extent.bottom + line_height
    ]
    glyph_left = min((extent.left for mark in leading if (extent := drawn_extent(mark)) is not None), default=first.x)
    padding = max(_LEAST_PADDING, min(glyph_left - drawn.left, drawn.right - max(w.x + w.width for w in words)))
    return _Label(marks, lines, space, line_height, leading, glyph_left, first.x - glyph_left, padding)


def least_width(group: Element, drawn: Extent) -> float | None:
    """The narrowest the element drawn in *group* at *drawn* may be sized: its longest word, and its first word
    after its glyph, each with the padding either side that `resized_element` keeps. None where it has no label.

    The label is set again by `resized_element` a word at a time and never breaks a word, so a narrower element
    would draw its words over its outline.
    """
    label = _label(group, drawn)
    if label is None:
        return None
    widest = max(word.width for line in label.lines for word in line)
    first = label.glyph_room + label.lines[0][0].width
    return max(widest, first) + 2 * label.padding


def resized_element(group: Element, drawn: Extent, to: Extent) -> Element:
    """An element's drawing at the size *to* states: outline stretched, glyph carried, label set again."""
    outline = list(group)[0]
    resized = _like(group)
    resized.append(fitted(outline, drawn, to))
    label = _label(group, drawn)
    if label is None:
        marks = [part for part in list(group)[1:] if tag_of(part) != "text"]
        middle = Motion.shift(to.centre.x - drawn.centre.x, to.centre.y - drawn.centre.y)
        resized.extend(moved(mark, middle) for mark in marks)
        return resized

    first = label.lines[0][0]
    space, line_height, glyph_room = label.space, label.line_height, label.glyph_room
    set_lines = _wrapped(_paragraphs(label.lines), to.width - 2 * label.padding, space, glyph_room)
    top = to.top + (to.height - len(set_lines) * line_height) / 2
    for row, line in enumerate(set_lines):
        baseline = top + row * line_height + line_height * _BASELINE_SHARE
        lead = glyph_room if row == 0 else 0.0
        x = to.left + (to.width - (lead + sum(word.width for word in line) + space * (len(line) - 1))) / 2
        if row == 0:
            beside = Motion.shift(x - label.glyph_left, baseline - first.baseline)
            resized.extend(moved(mark, beside) for mark in label.leading)
        x += lead
        for word in line:
            resized.append(_set_again(word, x, baseline))
            x += word.width + space
    corner = Motion.shift(to.right - drawn.right, to.top - drawn.top)
    resized.extend(moved(mark, corner) for mark in label.marks if all(mark is not led for led in label.leading))
    return resized
