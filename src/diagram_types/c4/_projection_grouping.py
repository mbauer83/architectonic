"""Which drawn elements a grouping is the boundary around.

C4 calls this a *group* and is explicit about what it is: a named grouping of elements that "will be
rendered as a boundary around those elements", and a purely visual construct — groups do not appear
as elements in the model at all. Two rules follow from its own definition and both are applied here,
because they are questions about membership rather than about drawing.
"""

from __future__ import annotations

from src.diagram_types.c4._projection_rollup import descendants
from src.diagram_types.c4._projection_vocabulary import GROUPING_TYPE, NESTING_TYPES, entity_type
from src.domain.relationships.derivation_types import ModelQuery


def grouping_membership(drawn: set[str], query: ModelQuery) -> tuple[tuple[str, str], ...]:
    """Which drawn elements each drawn grouping is the boundary around.

    Only members the level already draws are gathered. C4 groups hold elements of one abstraction
    level, and a grouping in this model is free to hold several — `Write Pipeline` gathers eleven
    components and an application interface, `Assurance Module` four components and three data
    objects. Filtering to what the level draws is what keeps a boundary from being asked to contain
    something the notation has no shape for.

    A grouping may hold another, which C4 permits and the resolver's nesting already handles.
    """
    return tuple(
        (member, group_id)
        for group_id in sorted(groupings(drawn, query))
        for member in sorted(
            descendants(group_id, query, nesting_types=NESTING_TYPES, max_depth=1) & drawn
        )
        if member != group_id
    )


def groupings(drawn: set[str], query: ModelQuery) -> set[str]:
    return {eid for eid in drawn if entity_type(eid, query) == GROUPING_TYPE}


def groupings_without_members(
    drawn: set[str], membership: tuple[tuple[str, str], ...], query: ModelQuery
) -> set[str]:
    """Groupings the level draws nothing inside, which are therefore not drawn at all.

    A group is a boundary, not an element: with no members on this level there is no boundary to
    draw, and a lone labelled box would say only that something exists somewhere else. That is what
    `Assurance Module` did on the container view — one box, none of its seven members, because they
    sit a level deeper than that view reaches.
    """
    holding = {group_id for _, group_id in membership}
    return groupings(drawn, query) - holding


