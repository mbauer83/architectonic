"""How a relationship is drawn: line style and the decoration at each end.

Structural, not pictorial. A notation says "hollow triangle at the target", never "realization" —
so a renderer can honour it without knowing any ontology's vocabulary, and a second modelling
language can declare its own relationships in the same terms.

This exists because `puml_arrow` cannot serve as the notation authority. It is one renderer's
spelling, and it cannot say everything a notation can — PlantUML has no form for a ball at the
source, so assignment is spelled `-->` there and loses its marker. Anything reading `puml_arrow`
to decide arrow shape draws different relationships identically, which is exactly what the graph
explorer did, rendering every ArchiMate relationship as one solid line with a filled head.

**What it does not mean.** This docstring used to argue that PlantUML "expresses containment by
nesting rather than by a diamond, so composition and aggregation are both spelled `-->` there", and
that reasoning kept both types' arrows markerless for as long as it stood. Nesting is indeed how
containment is drawn whenever it CAN be nested, and that stays the default. But the conclusion does
not follow, and PlantUML disproves it: `A o-- B` between two rectangles draws a hollow diamond at
A and `*--` a filled one — the project's own datatype diagrams had been spelling both all along.
A containment that cannot be nested — an element with two parents, a cycle, a member an authored
group claimed — falls back to an arrow, and there the diamond is what says which relation it is.
`tests/domain/test_arrow_spells_the_notation.py` now holds the two in agreement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

#: Line styles a relationship may be drawn with.
LineStyle = Literal["solid", "dashed", "dotted"]

#: Decorations that may sit at either end of a relationship.
EndMarker = Literal[
    "none",
    "open-arrow",
    "filled-arrow",
    "hollow-triangle",
    "filled-diamond",
    "hollow-diamond",
    "ball",
]

_LINE_STYLES: Final[frozenset[str]] = frozenset(("solid", "dashed", "dotted"))
_END_MARKERS: Final[frozenset[str]] = frozenset((
    "none", "open-arrow", "filled-arrow", "hollow-triangle",
    "filled-diamond", "hollow-diamond", "ball",
))


@dataclass(frozen=True, slots=True)
class RelationNotation:
    """The drawn form of one relationship type."""

    line: LineStyle = "solid"
    source: EndMarker = "none"
    target: EndMarker = "filled-arrow"

    def as_mapping(self) -> dict[str, str]:
        """Serializable form, for the read API and any renderer beyond this process."""
        return {"line": self.line, "source": self.source, "target": self.target}


#: What a relationship looks like when its type declares nothing. A plain directed line: the
#: least specific thing that can still be read as "from here to there".
DEFAULT_NOTATION: Final = RelationNotation()


def parse_relation_notation(raw: object) -> RelationNotation:
    """Read a `notation:` mapping from an ontology definition.

    Unknown or missing values fall back to the default rather than raising: an ontology that
    has not yet declared its notation should render plainly, not fail to load. A *misspelled*
    value is the case worth catching, and it is caught by the ontology's own conformance test
    rather than at load time, where the failure would be far from the edit that caused it.
    """
    if not isinstance(raw, dict):
        return DEFAULT_NOTATION
    line = str(raw.get("line", DEFAULT_NOTATION.line))
    source = str(raw.get("source", DEFAULT_NOTATION.source))
    target = str(raw.get("target", DEFAULT_NOTATION.target))
    return RelationNotation(
        line=line if line in _LINE_STYLES else DEFAULT_NOTATION.line,  # type: ignore[arg-type]
        source=source if source in _END_MARKERS else DEFAULT_NOTATION.source,  # type: ignore[arg-type]
        target=target if target in _END_MARKERS else DEFAULT_NOTATION.target,  # type: ignore[arg-type]
    )


#: The line of a PlantUML arrow token, per declared line style.
#:
#: `..` is **dashed**, not dotted — measured from what PlantUML emits, not assumed from the token's
#: appearance in source: `A ..> B` renders `stroke-dasharray:7,7`, identical to `-[dashed]->`, while
#: a genuinely dotted line is `stroke-dasharray:1,3` and needs the explicit `[dotted]` modifier.
#: Reading `..` as "dotted" is why two types declared a dotted line, spelled `..`, agreed with
#: themselves on paper and drew a dashed one.
_PUML_LINE: Final[dict[str, str]] = {"solid": "--", "dashed": "..", "dotted": "-[dotted]-"}

#: What a source-end decoration opens a token with. PlantUML has no form for a ball, so assignment
#: keeps a plain line — an honest approximation rather than a different relation's marker. An arrow
#: at the *source* is a line drawn back the way it is read, which is `<--`.
_PUML_SOURCE: Final[dict[str, str]] = {
    "filled-diamond": "*", "hollow-diamond": "o", "filled-arrow": "<", "open-arrow": "<",
}

#: What a target-end decoration closes a token with. PlantUML's arrow syntax draws one plain head,
#: so an open and a filled arrow are the same token there; the distinction survives in the notation
#: and is honoured by renderers that can draw it.
_PUML_TARGET: Final[dict[str, str]] = {
    "open-arrow": ">", "filled-arrow": ">", "hollow-triangle": "|>",
}


def puml_arrow_for(notation: RelationNotation) -> str:
    """The PlantUML arrow token that draws *notation*.

    One derivation, so a declaration and its spelling cannot disagree. They did: three ArchiMate
    types spelled a line their notation contradicts, and the macro include spelled a third version
    of the same fact for the bodies that use it.

    Not every notation has an exact PlantUML form — a ball at the source has none — so this is the
    closest legal token rather than a promise of fidelity. What it guarantees is that the token is
    *derived from* the declaration, so the two move together.
    """
    return (
        _PUML_SOURCE.get(notation.source, "")
        + _PUML_LINE[notation.line]
        + _PUML_TARGET.get(notation.target, "")
    )


def is_known_line_style(value: str) -> bool:
    return value in _LINE_STYLES


def is_known_end_marker(value: str) -> bool:
    return value in _END_MARKERS
