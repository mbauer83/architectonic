"""Writing a PlantUML ``legend`` block: the one place this project spells that syntax.

A legend is the only way a diagram can explain its own notation *inside the image*, which is what
makes it export with an SVG or a PNG rather than living beside them in a web page. PlantUML renders
the block outside the graph, so it costs the layout nothing — a legend drawn as real elements in a
container would be truer notation and would also let GraphViz place it wherever it liked.

**A table, because the marks are separable.** A reader turns colour, shape, glyph and arrow on and
off independently, and one drawn element carries all of its marks at once — so the marks cannot be
shown by drawing elements. A table's cells can each carry one mark: a background colour is a swatch,
a sprite reference draws the real glyph, and a shape or a line style is named in words because a cell
cannot draw either.

Vocabulary-free. It knows a row is cells and a cell may carry a colour, a sprite or text. What the
rows *mean* is the caller's, which is where the ontology lives.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.hex_colors import is_hex_color

#: Padding inside a swatch cell. A cell whose only content is a colour collapses to a few pixels
#: wide — measured — so the swatch is given a body to fill.
_SWATCH = "      "

#: Air around a cell's text. A creole table gives no control over cell padding, so the padding is the
#: content: without it every column sits hard against its dividing line.
_PAD = "  "

#: How the legend is presented.
#:
#: **The outer box goes.** PlantUML draws a border around the legend region *and* the table draws its
#: own, so a table legend arrives double-bordered and cramped. Dropping the region's border leaves the
#: dividing lines, which are the ones doing the work — they align each mark against its meaning.
#:
#: Emitted with the block rather than kept in the generated preamble, because it is a property of
#: *this* construct: a body carrying no legend should not carry a style rule for one. A body that
#: styles legends itself is overridden here, which is the right way round — the reader asked for this
#: legend, and it is not part of the authored diagram.
_STYLE = """\
<style>
legend {
  LineThickness 0
  BackgroundColor transparent
  Padding 12
  Margin 10
  FontSize 13
}
</style>"""


@dataclass(frozen=True)
class LegendCell:
    """One cell: a swatch, a glyph, or text. Whichever is set decides what the cell shows."""

    text: str = ""
    #: A `#rrggbb` fill, making this cell a colour swatch. Refused if it is not one, for the reason
    #: the reading-lens request refuses it: a cell colour is written into the block's own syntax.
    fill: str = ""
    #: A sprite *name* — the glyph is drawn by the same sprite the elements use, so a legend cannot
    #: show a glyph the picture does not.
    sprite: str = ""

    def spelled(self) -> str:
        colour = f"<{self.fill}>" if self.fill and is_hex_color(self.fill) else ""
        if self.sprite:
            return f"{colour}{_PAD}<${self.sprite}{{scale=1.0}}>{_PAD}"
        if self.text:
            return f"{colour}{_PAD}{_escaped(self.text)}{_PAD}"
        return f"{colour}{_SWATCH}" if colour else _PAD


@dataclass(frozen=True)
class LegendRow:
    cells: tuple[LegendCell, ...]
    #: A heading row, spelled with PlantUML's `|=` header cells. Needed because several sections share
    #: one table: without them a reader sees "rounded corners | capability" with nothing saying that
    #: the row is about shape.
    heading: bool = False


def _escaped(text: str) -> str:
    """Text that cannot break out of a cell.

    A `|` ends a cell and a newline ends a row, so either would turn one label into extra table — the
    same class of problem a `;` in a colour would be, and refused the same way rather than trusted.
    """
    return text.replace("|", "¦").replace("\n", " ").replace("\r", " ")


def legend_block(rows: Sequence[LegendRow], *, position: str = "bottom") -> str:
    """*rows* as a ``legend`` block, or nothing at all when there are no rows.

    Empty means empty: an author who asked for a legend of marks the diagram does not use gets no
    block rather than an empty bordered box, which would say "this diagram uses no notation".
    """
    if not rows:
        return ""
    width = max(len(row.cells) for row in rows)
    lines = [_STYLE, f"legend {position}"]
    for index, row in enumerate(rows):
        # A blank row before each section but the first. A creole table sets its row height from the
        # font and offers no padding, so an empty row is the only air available — and it reads as the
        # separator between sections that it is.
        if row.heading and index:
            lines.append("|" + "|".join(_PAD for _ in range(width)) + "|")
        separator = "|=" if row.heading else "|"
        lines.append(separator + separator.join(cell.spelled() for cell in row.cells) + "|")
    lines.append("endlegend")
    return "\n".join(lines) + "\n"


def with_legend(body: str, block: str) -> str:
    """*body* with *block* placed before its `@enduml`, or unchanged if there is no block.

    Before `@enduml` rather than appended, because a body ends with that line and PlantUML stops
    reading there — a legend after it is silently nothing. Inserted at the *last* one, so a body that
    quotes `@enduml` inside a label cannot end the diagram early.
    """
    if not block:
        return body
    marker = "@enduml"
    at = body.rfind(marker)
    if at == -1:
        return body + block
    return body[:at] + block + body[at:]
