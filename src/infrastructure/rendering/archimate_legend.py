"""The notation an ArchiMate body actually uses, as legend rows.

**Read out of the body's own preamble, not re-derived from the ontology.** The stereotype blocks and
sprite definitions a body carries are exactly what PlantUML is handed, so a legend built from them
describes the picture that was drawn. Deriving it from today's ontology instead would describe a
palette the diagram may not be using: a body carrying an older inlined copy renders in its own
colours, and this repository has had nine such diagrams at once. `ArchimateDeclarations` owns reading
that syntax and now answers both halves — which declarations a body refers to, and what each says.

**Only marks that occur.** The same convention the three exploration legends keep and the GSN
renderer keeps: a legend of everything declared is a catalogue, and a reader cannot tell which of its
rows are about the diagram in front of them.

This module is where the ArchiMate vocabulary legitimately sits — it is in `rendering/`, beside
`archimate_entity_declarations`, and it is named for it. `puml_legend` spells the block and knows none
of this; `diagram_reading_lens` colours elements and knows none of this either.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Literal

from src.application.puml_legend import LegendCell, LegendRow
from src.domain.ontology_representation.relation_notation import RelationNotation
from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations, StereotypeNotation

#: Which marks a reader can ask a diagram to explain. Each is independently switchable, because a
#: reader asking "what do the colours mean" is asking a different question from "what do the arrows
#: mean" — and one drawn element carries all of its marks at once, which is why the answer is a table
#: rather than a row of sample elements.
LegendMark = Literal["colour", "shape", "glyph", "arrow"]

#: The ontology's own prefix on a connection type, which a legend drops.
_ONTOLOGY_PREFIX = re.compile(r"^archimate[-_]")

#: What a corner shape says, in the words a legend shows. The shapes are the notation's own
#: vocabulary; what they *mean* in a given ontology is the ontology's, and saying only what is drawn
#: keeps this honest for a second modelling language.
_CORNER_WORDS: Mapping[str, str] = {
    "square": "square corners",
    "rounded": "rounded corners",
    "diagonal": "cut corners",
}

#: What an end marker looks like, said rather than drawn — a table cell cannot draw a line.
_MARKER_WORDS: Mapping[str, str] = {
    "none": "",
    "open-arrow": "open arrowhead",
    "filled-arrow": "filled arrowhead",
    "hollow-triangle": "hollow triangle",
    "filled-diamond": "filled diamond",
    "hollow-diamond": "hollow diamond",
    "ball": "ball",
}


def readable_label(name: str) -> str:
    """A declaration's key as a reader reads it.

    Three spellings arrive here and a legend is read by a human: a sprite key is
    `application_component`, a connection type is `archimate-assignment`, and a generated container's
    stereotype is `StrategyGrouping`. The ontology prefix goes — the same thing the search result
    labels do with it, and for the same reason: it says which modelling language this is, which a
    reader of an ArchiMate diagram already knows.

    The prefix is **named**, not matched as "a leading segment". Guessing turned
    `application_component` into `component`, because nothing in the shape of a name distinguishes an
    ontology prefix from the first word of a two-word type. This module is the one that legitimately
    knows the vocabulary — that is why it is in `rendering/` and named for it — so it says which prefix
    it means.
    """
    stripped = _ONTOLOGY_PREFIX.sub("", name, count=1)
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stripped)
    return spaced.replace("_", " ").replace("-", " ").lower()


def _heading(*labels: str) -> LegendRow:
    return LegendRow(tuple(LegendCell(text=label) for label in labels), heading=True)


def _arrow_words(notation: RelationNotation) -> str:
    ends = [
        f"{_MARKER_WORDS.get(notation.source, notation.source)} at the source"
        if notation.source != "none" else "",
        f"{_MARKER_WORDS.get(notation.target, notation.target)} at the target"
        if notation.target != "none" else "",
    ]
    return ", ".join(part for part in [f"{notation.line} line", *ends] if part)


def colour_rows(fills: Mapping[str, str], *, means: str) -> tuple[LegendRow, ...]:
    """One row per colour in use, given as label → `#rrggbb`.

    Taken as a mapping rather than computed here, because *what* a colour means depends on why the
    diagram is coloured: by default a fill says which kind of element this is, and under an ad-hoc
    reading it says where an attribute's value sits. The caller knows which question is being asked,
    and *means* is how the heading says so — a legend headed "element kind" beside a heat map would be
    describing the wrong question.

    Grouped **by colour**, not by label. Two element kinds in one domain are drawn the same colour, so
    listing each separately gives a reader two rows with identical swatches and no way to tell which
    row explains the box in front of them — the colour is the mark, and the mark is what a legend row
    is about.
    """
    grouped: dict[str, list[str]] = {}
    for label, fill in fills.items():
        if fill:
            grouped.setdefault(fill, []).append(label)
    if not grouped:
        return ()
    return (_heading("colour", means), *(
        LegendRow((LegendCell(fill=fill), LegendCell(text=", ".join(labels))))
        for fill, labels in grouped.items()
    ))


def shape_rows(notations: Mapping[str, StereotypeNotation]) -> tuple[LegendRow, ...]:
    """One row per corner shape in use, naming the stereotypes drawn with it.

    Grouped by shape rather than listed per stereotype: a corner shape says what *kind* of thing an
    element is, so twelve motivation types drawn with cut corners are one fact, not twelve rows.
    """
    grouped: dict[str, list[str]] = {}
    for name, notation in sorted(notations.items()):
        grouped.setdefault(notation.corner, []).append(readable_label(name))
    rows = tuple(
        LegendRow((
            LegendCell(text=_CORNER_WORDS.get(corner, corner)),
            LegendCell(text=", ".join(names)),
        ))
        for corner, names in sorted(grouped.items())
        if names
    )
    return (_heading("shape", "element kinds"), *rows) if rows else ()


def glyph_rows(sprites: Sequence[str]) -> tuple[LegendRow, ...]:
    """One row per glyph the body draws, showing the glyph itself.

    The sprite is referenced by the same name the element labels reference, so the legend cannot show
    a glyph the picture does not — and cannot show one whose definition the body lacks, which would
    render as an empty cell.
    """
    rows = tuple(
        LegendRow((
            LegendCell(sprite=f"archimate_{name}"),
            LegendCell(text=readable_label(name)),
        ))
        for name in sorted(sprites)
    )
    return (_heading("glyph", "element kind"), *rows) if rows else ()


def arrow_rows(notations: Mapping[str, RelationNotation]) -> tuple[LegendRow, ...]:
    """One row per relationship type drawn, describing its line in words."""
    rows = tuple(
        LegendRow((LegendCell(text=readable_label(name)), LegendCell(text=_arrow_words(notation))))
        for name, notation in sorted(notations.items())
    )
    return (_heading("relationship", "drawn as"), *rows) if rows else ()


def notations_referenced_in(body: str, declarations: ArchimateDeclarations) -> dict[str, StereotypeNotation]:
    """What each stereotype the body uses says about how its elements are drawn.

    A reference the declarations do not know is dropped: a body may carry a stereotype from a module
    that is not loaded, and a legend row for it could say nothing about how it looks.
    """
    referenced = declarations.referenced_in(body)
    found = ((name, declarations.notation_of(name)) for name in referenced.stereotypes)
    return {name: notation for name, notation in found if notation is not None}
