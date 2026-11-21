"""Which stated relation each relation drawn on a picture is.

A layout states a route by the diagram's key for a drawn relation; a picture knows a relation only by
the aliases of its two ends, in the order the renderer names them, which is not the relation's own.
The join is made here once, for the composer and for anything else that has to say which drawn line
is which.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.domain.diagrams.layout.laid_out_diagram import LaidOutDiagram
from src.domain.diagrams.layout.rendered_picture import RenderedPicture


@dataclass(frozen=True)
class DrawnAs:
    """A stated relation's key, and whether the picture draws it from its target to its source."""

    key: str
    turned: bool


def relation_keys_by_index(picture: RenderedPicture, diagram: LaidOutDiagram) -> dict[int, DrawnAs]:
    """Each relation of *picture*, by its index, as the relation *diagram* states.

    Several relations between one pair are matched in order: the picture's and the diagram's. A drawn
    relation the diagram does not state is absent.
    """
    waiting: dict[frozenset[str], list[int]] = defaultdict(list)
    for index, relation in enumerate(picture.relations):
        waiting[frozenset(relation.ends)].append(index)
    keyed: dict[int, DrawnAs] = {}
    for key, (source, target) in diagram.relations.items():
        if between := waiting.get(frozenset((source, target))):
            index = between.pop(0)
            keyed[index] = DrawnAs(key, picture.relations[index].ends[0] != source)
    return keyed
