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

from src.application.puml_alias_declarations import overrides_colour
from src.application.puml_legend import LegendRow, legend_block, with_legend
from src.application.viewpoints.diagram_reading_lens import ReadingLens
from src.domain.ontology_representation.relation_notation import RelationNotation
from src.domain.viewpoints.viewpoint_style_values import (
    AD_HOC_RAMP_TOKENS,
    DEFAULT_ATTRIBUTE_GRADIENT,
    graded_colors,
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
    nesting_rows,
    notations_referenced_in,
    readable_label,
    shape_rows,
)


def _attribute_colouring(
    lens: ReadingLens, members: Sequence[str], unset: str | None
) -> dict[str, str]:
    """What the reader's own colouring means, or nothing when they set none.

    The attribute names itself once, in the section heading — `means` carries it. Prefixing every row
    with it too read "Lifecycle State | Lifecycle State: Planned" across the widest column in the
    table, and pushed the swatches away from the values they stand for.
    """
    if not lens.colour_by:
        return {}
    if members:
        return {
            member: lens.key.get(member, colour)
            for member, colour in graded_colors(
                members, unset=unset, gradient=lens.gradient or DEFAULT_ATTRIBUTE_GRADIENT
            )
        }
    near, far = lens.ramp if lens.ramp is not None else AD_HOC_RAMP_TOKENS
    return {"lower": token_color(near), "higher": token_color(far)}


def _element_kind_colouring(
    body: str,
    declarations: ArchimateDeclarations,
    notations: Mapping[str, StereotypeNotation],
    declared_labels: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The stereotype fills still on screen, which is not the same as the ones the body references.

    **Both colourings can be present at once**, and the first version of this missed it. An ad-hoc
    colouring recolours only the entities carrying a value for the attribute, so a diagram under one
    shows the attribute's palette on those and each stereotype's own fill on the rest. Replacing the
    element-kind rows with the attribute's — on the stated grounds that the picture "no longer uses"
    them — left every unvalued box unexplained. Measured on a real view: two elements recoloured, six
    still showing their stereotype fill, and the legend named only the attribute.

    The other direction matters too, which is why this reads the body rather than assuming: where every
    element of a stereotype *was* recoloured, that fill is genuinely gone and naming it would send a
    reader looking for a colour that is not there.

    A declaration carrying its own colour suffix is one whose fill was overridden — asked of
    `overrides_colour`, the module that owns reading a declaration. Only the fill is overridden, so the
    shape and glyph sections are unaffected and read every referenced stereotype as before.

    Through the same spelling the other sections use: this had its own `_`-to-space replacement, so one
    legend read `StrategyGrouping` in its colour rows and `strategy grouping` in its shape rows — two
    labels for one thing, in one table.
    """
    still_showing: set[str] = set()
    for line in body.splitlines():
        if overrides_colour(line):
            continue
        # Through `referenced_in`, which owns reading a stereotype reference and works on any text —
        # one line as readily as a whole body. Spelling the `<<name>>` pattern again here is what the
        # syntax register exists to stop.
        still_showing.update(declarations.referenced_in(line).stereotypes)
    return {
        readable_label(name, declared_labels): notation.fill
        for name, notation in sorted(notations.items())
        if name in still_showing
    }


def body_with_reading_legend(
    body: str,
    *,
    lens: ReadingLens,
    declarations: ArchimateDeclarations,
    members: Sequence[str] = (),
    unset: str | None = None,
    declared_labels: Mapping[str, str] | None = None,
    connection_notations: Mapping[str, RelationNotation] | None = None,
    nested_types: Sequence[str] = (),
) -> str:
    """*body* with the legend the reader asked for, or unchanged when they asked for none.

    *members* are the declared values of the attribute being coloured by, where it has a bounded set —
    the same list the lens assigns member colours from, so the key and the picture agree by
    construction rather than by both being computed correctly.
    """
    if not lens.legend:
        return body
    return with_legend(body, legend_block(_rows_for(
        body, lens=lens, declarations=declarations, members=members, unset=unset,
        connection_notations=connection_notations, nested_types=nested_types,
        declared_labels=declared_labels,
    )))


def _rows_for(
    body: str,
    *,
    lens: ReadingLens,
    declarations: ArchimateDeclarations,
    members: Sequence[str] = (),
    unset: str | None = None,
    declared_labels: Mapping[str, str] | None = None,
    connection_notations: Mapping[str, RelationNotation] | None = None,
    nested_types: Sequence[str] = (),
) -> tuple[LegendRow, ...]:
    """Every section the diagram has something to say in, in a fixed order.

    Every one, because the reader asked for *the* legend rather than for a selection of marks: which
    marks a diagram carries is the diagram's answer. A section with no rows contributes nothing, so a
    diagram with no glyphs simply has no glyph section — the same "list what is present" convention
    every legend in this product keeps.
    """
    notations = notations_referenced_in(body, declarations)
    return (
        # Two colour sections rather than one, because a fill can mean two things at once on the same
        # picture: the reader's attribute where a value exists, and the element's kind where it does
        # not. Either may be empty and contribute no section.
        *colour_rows(_attribute_colouring(lens, members, unset), means=lens.colour_by),
        *colour_rows(
            _element_kind_colouring(body, declarations, notations, declared_labels), means="element kinds"
        ),
        *shape_rows(notations, declared_labels),
        *glyph_rows(sorted(declarations.referenced_in(body).sprites), declared_labels),
        *arrow_rows(connection_notations or {}, declared_labels),
        *nesting_rows(nested_types, declared_labels),
    )


def can_explain_notation(
    body: str,
    *,
    declarations: ArchimateDeclarations,
    connection_notations: Mapping[str, RelationNotation] | None = None,
    nested_types: Sequence[str] = (),
) -> bool:
    """Whether a legend for this body would say anything at all.

    Answered by building the rows and seeing whether there are any, rather than by a second rule
    about what counts as "having notation": the row builders already decide that, and a parallel test
    could disagree with the legend a reader then gets.

    It is what lets a surface withhold the control. A legend checkbox on a diagram with no
    stereotypes, no glyphs and no relationships does nothing, and a reader cannot tell that from a
    legend that failed.
    """
    return bool(_rows_for(
        body,
        lens=ReadingLens(legend=True),
        declarations=declarations,
        connection_notations=connection_notations,
        nested_types=nested_types,
    ))


