"""A diagram's legend, written into the image and describing only the notation it carries.

**Into the image**, because that is the requirement: a legend beside the picture in a web page does
not survive a download, and "export what I am looking at" is the whole point of the reading surface.
So it is a PlantUML `legend` block, and `puml_legend` is the one place that spells one.

**Only what occurs.** The convention every legend in this product already keeps — the three
exploration legends and the GSN renderer's own — because a legend of everything declared is a
catalogue, and a reader cannot tell which of its rows are about the diagram in front of them.

The cell contents are the sharp part. A cell is separated by `|` and a row by a newline, so a label
carrying either would not be a bad label: it would be extra table. And a colour is written into the
block's syntax, which is the same reason the reading-lens request refuses anything but six hex digits.
"""

from __future__ import annotations

from src.application.puml_legend import LegendCell, LegendRow, legend_block, with_legend

_BODY = "@startuml x\nrectangle \"A\" as A\n@enduml\n"


class TestHowItIsPresented:
    def test_the_legend_region_loses_its_own_border(self) -> None:
        """PlantUML draws a border around the region *and* the table draws its own, so a table legend
        arrives double-bordered and cramped. The dividing lines are the ones doing the work."""
        block = legend_block((LegendRow((LegendCell(text="a"),)),))

        assert "<style>" in block
        assert "LineThickness 0" in block

    def test_a_blank_row_separates_sections(self) -> None:
        """A creole table sets its row height from the font and offers no padding, so an empty row is
        the only air available — and it reads as the separator between sections that it is."""
        block = legend_block((
            LegendRow((LegendCell(text="colour"), LegendCell(text="kinds")), heading=True),
            LegendRow((LegendCell(fill="#dc2626"), LegendCell(text="a"))),
            LegendRow((LegendCell(text="shape"), LegendCell(text="kinds")), heading=True),
            LegendRow((LegendCell(text="rounded"), LegendCell(text="b"))),
        ))

        rows = [line for line in block.splitlines() if line.startswith("|")]
        assert rows[2].replace("|", "").strip() == ""
        assert rows[3].startswith("|=")

    def test_the_first_section_gets_no_leading_blank(self) -> None:
        block = legend_block((
            LegendRow((LegendCell(text="colour"), LegendCell(text="kinds")), heading=True),
            LegendRow((LegendCell(fill="#dc2626"), LegendCell(text="a"))),
        ))

        assert [line for line in block.splitlines() if line.startswith("|")][0].startswith("|=")


class TestWhereTheBlockGoes:
    def test_a_block_is_placed_before_the_enduml(self) -> None:
        """A body ends at `@enduml` and PlantUML stops reading there, so an appended legend is
        silently nothing at all."""
        block = legend_block((LegendRow((LegendCell(text="a"),)),))

        placed = with_legend(_BODY, block)

        assert placed.index("legend bottom") < placed.index("@enduml")
        assert placed.rstrip().endswith("@enduml")

    def test_the_last_enduml_is_the_one_that_ends_the_diagram(self) -> None:
        """A label may quote `@enduml`; splitting at the first would end the diagram early."""
        body = '@startuml x\nrectangle "mentions @enduml here" as A\n@enduml\n'

        placed = with_legend(body, legend_block((LegendRow((LegendCell(text="a"),)),)))

        assert placed.count("@enduml") == 2
        assert placed.index("legend bottom") > placed.index("mentions @enduml here")

    def test_no_rows_means_no_block_rather_than_an_empty_box(self) -> None:
        """A reader who asked to have marks explained that the diagram does not use gets nothing —
        an empty bordered box would say "this diagram uses no notation"."""
        assert legend_block(()) == ""
        assert with_legend(_BODY, "") == _BODY


class TestWhatACellMayCarry:
    def test_a_colour_becomes_a_swatch_with_a_body_to_fill(self) -> None:
        """A cell whose only content is a colour collapses to a few pixels wide — measured — so the
        swatch is padded."""
        spelled = LegendCell(fill="#dc2626").spelled()

        assert spelled.startswith("<#dc2626>")
        assert len(spelled) > len("<#dc2626>")

    def test_a_colour_that_is_not_six_hex_digits_is_not_written(self) -> None:
        """The cell colour goes into the block's own syntax, so a value carrying a `;` or a `|` would
        be extra markup rather than a bad colour."""
        assert LegendCell(fill="dc2626;line:000000", text="x").spelled().count("<") == 0
        assert LegendCell(fill="red", text="x").spelled().count("<") == 0

    def test_a_sprite_is_referenced_by_name_rather_than_drawn(self) -> None:
        """The same sprite the element labels reference, so a legend cannot show a glyph the picture
        does not — nor one whose definition the body lacks, which renders as an empty cell."""
        assert "<$archimate_capability{scale=1.0}>" in LegendCell(sprite="archimate_capability").spelled()

    def test_a_label_cannot_end_its_own_cell(self) -> None:
        assert "|" not in LegendCell(text="a | b").spelled()

    def test_a_label_cannot_end_its_own_row(self) -> None:
        assert "\n" not in LegendCell(text="a\nb").spelled()
        assert "\r" not in LegendCell(text="a\rb").spelled()

    def test_a_heading_row_is_spelled_as_one(self) -> None:
        """Several sections share one table, so without headings a reader sees "rounded corners |
        capability" with nothing saying the row is about shape."""
        block = legend_block((
            LegendRow((LegendCell(text="shape"), LegendCell(text="element kinds")), heading=True),
            LegendRow((LegendCell(text="rounded corners"), LegendCell(text="capability"))),
        ))

        assert "|=  shape  |=  element kinds  |" in block
        assert "|  rounded corners  |  capability  |" in block
