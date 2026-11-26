"""What a diagram's body draws that a body generated from its composition would not.

A diagram owns its PlantUML body (ADR@1783406738): a body an author wrote is kept, and only a body the
generator wrote is the generator's to write again. A canvas save, a whole-diagram replacement and an
automatic layout all write a body generated from the diagram's composition, so each must first know
whether doing so discards anything. That is answered by comparison, not by a flag: the stored body
against the body its own composition generates. What the first draws and the second does not — a box
the composition does not state, a further drawing of an element, an arrow the model does not hold — was
put there by hand, and regenerating would lose it. So is a direction the body states that the generated body
does not: a picture an author turned on its side.

Read through the owners of each syntax: groupings by `puml_grouping_parsing`, declarations by
`puml_alias_declarations`, relations by `puml_relation_parsing`. A relation is compared without its
direction, so drawing the same pair the other way round is not counted as hand-drawn.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from src.application.puml_alias_declarations import alias_declared_on
from src.application.puml_grouping_parsing import parse_labeled_groupings
from src.application.puml_relation_parsing import declared_relations

#: A statement of the direction the picture is laid out in, on a line of its own.
_DIRECTION = re.compile(r"^\s*(?P<direction>left to right|top to bottom)\s+direction\s*$", re.MULTILINE)
#: The direction PlantUML lays a picture out in where its body states none.
_PLANTUMLS_DIRECTION = "top to bottom direction"


@dataclass(frozen=True)
class HandDrawnRelation:
    """A relation only the body draws, by the aliases of its two ends; its type is the model's to say."""

    source_alias: str
    target_alias: str


@dataclass(frozen=True)
class HandDrawn:
    """The boxes (by label), declarations (by alias), relations (by their two aliases) and direction only the
    body draws.

    Aliases are the body's own spelling, which a reader never sees: whoever reports these names them first
    (`diagram_body_ownership.named_hand_drawn`).
    """

    boxes: tuple[str, ...] = ()
    elements: tuple[str, ...] = ()
    relations: tuple[HandDrawnRelation, ...] = ()
    directions: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.boxes or self.elements or self.relations or self.directions)


def _boxes(body: str) -> Counter[str]:
    return Counter(grouping.label for grouping in parse_labeled_groupings(body))


def _declarations(body: str) -> set[str]:
    return {declaration.alias for line in body.splitlines() if (declaration := alias_declared_on(line))}


def _directions(body: str) -> set[str]:
    """The directions *body* states; none states PlantUML's own, top to bottom, so stating that is no change."""
    return {f"{match['direction']} direction" for match in _DIRECTION.finditer(body)} or {_PLANTUMLS_DIRECTION}


def _relations(body: str) -> dict[frozenset[str], HandDrawnRelation]:
    return {
        frozenset((relation.source_alias, relation.target_alias)):
            HandDrawnRelation(relation.source_alias, relation.target_alias)
        for relation in declared_relations(body, {})
    }


def hand_drawn(body: str, generated: str) -> HandDrawn:
    """What *body* draws that *generated* — the body its composition generates — does not."""
    generated_relations = _relations(generated)
    return HandDrawn(
        boxes=tuple(sorted(_boxes(body) - _boxes(generated))),
        elements=tuple(sorted(_declarations(body) - _declarations(generated))),
        relations=tuple(sorted(
            (relation for pair, relation in _relations(body).items() if pair not in generated_relations),
            key=lambda relation: (relation.source_alias, relation.target_alias),
        )),
        directions=tuple(sorted(_directions(body) - _directions(generated))),
    )
