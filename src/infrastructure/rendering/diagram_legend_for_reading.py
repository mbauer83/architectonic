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
from dataclasses import dataclass
from pathlib import Path

from src.application.puml_alias_declarations import overrides_colour
from src.application.puml_legend import LegendRow, legend_block, with_legend
from src.application.puml_relation_parsing import declared_relations
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
    nesting_rows,
    notations_referenced_in,
    readable_label,
    shape_rows,
)


def _attribute_colouring(lens: ReadingLens, members: Sequence[str]) -> dict[str, str]:
    """What the reader's own colouring means, or nothing when they set none.

    The attribute names itself once, in the section heading — `means` carries it. Prefixing every row
    with it too read "Lifecycle State | Lifecycle State: Planned" across the widest column in the
    table, and pushed the swatches away from the values they stand for.
    """
    if not lens.colour_by:
        return {}
    if members:
        return {member: lens.key.get(member, colour) for member, colour in categorical_colors(members)}
    near, far = lens.ramp if lens.ramp is not None else AD_HOC_RAMP_TOKENS
    return {"lower": token_color(near), "higher": token_color(far)}


def _element_kind_colouring(
    body: str, declarations: ArchimateDeclarations, notations: Mapping[str, StereotypeNotation]
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
        readable_label(name): notation.fill
        for name, notation in sorted(notations.items())
        if name in still_showing
    }


def body_with_reading_legend(
    body: str,
    *,
    lens: ReadingLens,
    declarations: ArchimateDeclarations,
    members: Sequence[str] = (),
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
        body, lens=lens, declarations=declarations, members=members,
        connection_notations=connection_notations, nested_types=nested_types,
    )))


def _rows_for(
    body: str,
    *,
    lens: ReadingLens,
    declarations: ArchimateDeclarations,
    members: Sequence[str] = (),
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
        *colour_rows(_attribute_colouring(lens, members), means=lens.colour_by),
        *colour_rows(_element_kind_colouring(body, declarations, notations), means="element kinds"),
        *shape_rows(notations),
        *glyph_rows(sorted(declarations.referenced_in(body).sprites)),
        *arrow_rows(connection_notations or {}),
        *nesting_rows(nested_types),
    )


@dataclass(frozen=True)
class NotationInUse:
    """What notation one diagram carries: what its stereotypes declare, and how its relationships draw.

    Assembled once because two surfaces need the same pair and were building it separately — the route
    that offers the legend control and the route that draws the legend. That is the drift
    `can_explain_notation` was written to avoid, reappearing one level up: a control offered from one
    reading of the notation and a legend drawn from another can disagree, and the reader sees a
    checkbox that does nothing.
    """

    declarations: ArchimateDeclarations
    connection_notations: dict[str, RelationNotation]
    #: The relationship types this body draws by containment rather than as a line. Its own field
    #: because the two are answered by one reading of the body and a caller needs both.
    nested_types: tuple[str, ...] = ()


def notation_in_use(
    body: str,
    placed_connections: Sequence[tuple[str, str, str]],
    *,
    repo_root: Path,
    relation_notations: Mapping[str, Mapping[str, str]],
) -> NotationInUse:
    """The notation a diagram carries, given the connections it records and the body it stores.

    *placed_connections* are `(connection_type, source_alias, target_alias)`. Only the types this body
    draws as **lines** get a relationship notation — a composition rendered as containment is in the
    model and is not a line, and `types_drawn_as_lines` is what decides.

    *relation_notations* is passed in rather than read here: which catalog holds them is the caller's
    to know, and this module has no business resolving one.

    The declarations are the repository's, not this diagram's — every diagram is handed the same
    generated includes, and which of them a given body *references* is decided later, by
    `notations_referenced_in`, off that body.
    """
    return NotationInUse(
        declarations=ArchimateDeclarations.from_repo(repo_root),
        connection_notations=notations_for_connection_types(
            sorted(types_drawn_as_lines(body, connections=placed_connections)), relation_notations
        ),
        nested_types=tuple(sorted(types_drawn_as_nesting(body, connections=placed_connections))),
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


def types_drawn_as_nesting(
    body: str, *, connections: Sequence[tuple[str, str, str]]
) -> frozenset[str]:
    """Which relationship types this body draws by putting one element **inside** another.

    The complement of `types_drawn_as_lines` over the same reading, and not its negation: a connection
    the body draws *nowhere* is neither, and giving it either row would explain a mark the reader
    cannot find. `declared_relations` reports a containment with an empty arrow, which is the test.
    """
    nested = {
        (relation.source_alias, relation.target_alias)
        for relation in declared_relations(body, {})
        if not relation.arrow
    }
    return frozenset(
        conn_type for conn_type, source, target in connections if (source, target) in nested
    )


def types_drawn_as_lines(
    body: str, *, connections: Sequence[tuple[str, str, str]]
) -> frozenset[str]:
    """Which relationship types this body actually draws as a **line**.

    *connections* are `(connection_type, source_alias, target_alias)` for the connections the diagram
    records. A type is returned when at least one of its pairs is drawn with an arrow — not when the
    model merely records it.

    **Because a relationship can be in the model and not be a line.** PlantUML draws composition and
    aggregation as containment, and this project's ontology classes both as `nesting`, so the renderer
    puts the child inside the parent and emits no arrow. Reading the relationship rows from the model
    put a filled diamond for composition and a hollow one for aggregation into the legend of a picture
    that contained neither: `promote-artifacts` nests eight functions inside one process and draws
    eleven `-->` and one `..|>`, and nothing else. A legend explaining a mark the reader cannot find is
    worse than one that omits it.

    **Not by excluding the nesting-class types**, which would be the obvious shortcut and is wrong:
    `build_visual_nesting` treats a structural edge as a *proposal*, honoured only where it keeps the
    drawing a forest, so a composition to a second parent stays an arrow. What a type is drawn as is a
    property of this body, so it is read from this body.

    Through `declared_relations`, which owns reading the relations a body draws — including the ones
    stated by nesting, which it reports with an empty arrow. That is the whole test: an empty arrow is
    containment, a non-empty one is a line, and a pair it does not report at all is drawn nowhere.
    """
    lines = {
        (relation.source_alias, relation.target_alias)
        for relation in declared_relations(body, {})
        if relation.arrow
    }
    return frozenset(
        conn_type for conn_type, source, target in connections if (source, target) in lines
    )


def notations_for_connection_types(
    conn_types: Sequence[str], relation_notations: Mapping[str, Mapping[str, str]]
) -> dict[str, RelationNotation]:
    """How each of *conn_types* is drawn, keyed by the type.

    Which types those are is `types_drawn_as_lines`' answer, not this function's: it is handed the ones
    the picture draws as lines and says what each looks like.

    Through `parse_relation_notation`, which is the one reader of that declaration — the catalogue
    hands out plain mappings so it can serve the read API, and parsing one here by hand would be a
    second opinion about what an absent field defaults to.
    """
    return {
        conn_type: parse_relation_notation(relation_notations[conn_type])
        for conn_type in sorted(set(conn_types))
        if conn_type in relation_notations
    }
