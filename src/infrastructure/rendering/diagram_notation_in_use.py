"""Which marks a stored diagram's body actually uses.

Split from `diagram_legend_for_reading`, which composes the legend, because these answer a different
question and the pair had grown past the soft length policy holding both. The distinction is not
cosmetic: it is the one this release kept getting wrong.

**What a mark looks like comes from the model; whether the picture uses it comes from the body.** A
PlantUML arrow token cannot serve as the notation authority — it has no form for a ball at the source,
so reading one back would describe several relationships identically. But the model records
relationships the picture may draw as *containment* rather than as a line, and it records attributes
that recolour only some of the elements, so a legend built from the model alone explains marks that are
not on screen. Twice this release it did.

Every answer here is therefore read from the body, through the modules that own reading it —
`declared_relations` for relations, `referenced_in` for stereotype references, `overrides_colour` for a
declaration's own fill. None of those patterns is spelled a second time here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.application.puml_relation_parsing import declared_relations
from src.domain.ontology_representation.relation_notation import RelationNotation, parse_relation_notation
from src.infrastructure.rendering._archimate_includes import ArchimateDeclarations


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
