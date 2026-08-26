"""The legend for a diagram as a reader is currently looking at it.

The composition step: what `archimate_legend` reads out of the body, what the reading lens is
colouring by, and `puml_legend`'s spelling of a block. It exists because the *colour* legend is the
one mark whose meaning changes with the display — by default a fill says which kind of element this
is, and under an ad-hoc colouring it says where an attribute's value sits — and something has to know
which question is being asked. Nothing else does: the lens knows the colouring but not the notation,
and the notation reader knows the marks but not why the diagram is coloured.

Kept out of the lens on purpose. A legend is appended to a body, not woven into its element lines, so
it composes as a second step over the same body — which keeps `apply_reading_lens` about elements and
lets a reader ask for a legend on an otherwise untouched diagram.

**Arrows come from the model, not from the picture.** The relationship types drawn are the diagram's
own recorded connections, and how each is drawn is `relation_notation` — which exists precisely
because a PlantUML arrow token cannot serve as the notation authority: it has no form for a ball at
the source, so reading one back would describe several relationships identically. The other three
marks come from the body, because for those the body's preamble *is* what PlantUML was handed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.application.puml_legend import LegendRow, legend_block, with_legend
from src.application.viewpoints.diagram_reading_lens import ReadingLens
from src.domain.ontology_representation.relation_notation import RelationNotation, parse_relation_notation
from src.domain.viewpoints.viewpoint_style_values import (
    AD_HOC_RAMP_TOKENS,
    categorical_colors,
    token_color,
)
from src.infrastructure.rendering._archimate_includes import (
    ArchimateDeclarations,
    StereotypeNotation,
)
from src.infrastructure.rendering.archimate_legend import (
    arrow_rows,
    colour_rows,
    glyph_rows,
    notations_referenced_in,
    readable_label,
    shape_rows,
)


def _colouring_in_use(
    lens: ReadingLens, members: Sequence[str], notations: Mapping[str, StereotypeNotation]
) -> dict[str, str]:
    """What the fills mean *now*: the attribute's values, or the kinds of element.

    Under an ad-hoc colouring the fills are the reader's own, so the legend must show those — a legend
    still listing element kinds beside a heat map would describe colours the picture no longer uses,
    which is worse than no legend. The colours come from the same functions the lens renders with, so
    the two cannot drift.
    """
    if not lens.colour_by:
        # Through the same spelling the other sections use: this had its own `_`-to-space replacement,
        # so one legend read `StrategyGrouping` in its colour rows and `strategy grouping` in its shape
        # rows — two labels for one thing, in one table.
        return {readable_label(name): notation.fill for name, notation in sorted(notations.items())}
    if members:
        return {
            f"{lens.colour_by}: {member}": lens.key.get(member, colour)
            for member, colour in categorical_colors(members)
        }
    near, far = lens.ramp if lens.ramp is not None else AD_HOC_RAMP_TOKENS
    return {
        f"{lens.colour_by}: lower": token_color(near),
        f"{lens.colour_by}: higher": token_color(far),
    }


def body_with_reading_legend(
    body: str,
    *,
    lens: ReadingLens,
    declarations: ArchimateDeclarations,
    members: Sequence[str] = (),
    connection_notations: Mapping[str, RelationNotation] | None = None,
) -> str:
    """*body* with the legend the reader asked for, or unchanged when they asked for none.

    *members* are the declared values of the attribute being coloured by, where it has a bounded set —
    the same list the lens assigns member colours from, so the key and the picture agree by
    construction rather than by both being computed correctly.
    """
    if not lens.legends:
        return body
    notations = notations_referenced_in(body, declarations)
    rows: list[LegendRow] = []
    if "colour" in lens.legends:
        rows += colour_rows(
            _colouring_in_use(lens, members, notations),
            means=lens.colour_by if lens.colour_by else "element kinds",
        )
    if "shape" in lens.legends:
        rows += shape_rows(notations)
    if "glyph" in lens.legends:
        rows += glyph_rows(sorted(declarations.referenced_in(body).sprites))
    if "arrow" in lens.legends:
        rows += arrow_rows(connection_notations or {})
    return with_legend(body, legend_block(tuple(rows)))


def notations_for_connection_types(
    conn_types: Sequence[str], relation_notations: Mapping[str, Mapping[str, str]]
) -> dict[str, RelationNotation]:
    """How each drawn relationship type is drawn, keyed by the type.

    Through `parse_relation_notation`, which is the one reader of that declaration — the catalogue
    hands out plain mappings so it can serve the read API, and parsing one here by hand would be a
    second opinion about what an absent field defaults to.
    """
    return {
        conn_type: parse_relation_notation(relation_notations[conn_type])
        for conn_type in sorted(set(conn_types))
        if conn_type in relation_notations
    }
