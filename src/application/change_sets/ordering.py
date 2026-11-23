"""The order a set's operations are applied in — derived, never authored.

An authored order is a second statement of something the operations already say. A connection that
names an entity the set creates has to come after the create; an entity the set removes has to go
after the connections the set removes from it. Those are the only orderings a set needs, and they
are read off the operations, so a set cannot carry an order that contradicts its own content and two
machines cannot apply one set differently.

**One set may be read on top of others.** The lower ones are applied first, each as its own set, and
the upper may name what any of them creates. Which sets are beneath which is not decided here: a
caller hands over the sets beneath, lowest first, or none.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from graphlib import CycleError, TopologicalSorter

from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.coherence import dangling
from src.application.change_sets.operations import (
    MalformedChangeSet,
    Operation,
    OperationKey,
    RemoveConnection,
    RemoveEntity,
    entities_used,
    sort_key,
)

#: For each operation's claim, the claims of the operations that must be applied before it.
Dependencies = Mapping[OperationKey, frozenset[OperationKey]]


def dependencies(change_set: ChangeSet) -> Dependencies:
    """What each operation of the set needs applied first, among the set's own operations.

    Two kinds of edge, and only two: an operation after the create of each entity it uses, and the
    removal of an entity after the removal of each of its connections.
    """
    created = change_set.created
    removed_connections = [op for op in change_set.operations if isinstance(op, RemoveConnection)]

    def needed_by(operation: Operation) -> frozenset[OperationKey]:
        needs = {created[used].claim for used in entities_used(operation) if used in created}
        if isinstance(operation, RemoveEntity):
            needs |= {
                removal.claim
                for removal in removed_connections
                if operation.target in removal.address.endpoints
            }
        return frozenset(needs)

    return {operation.claim: needed_by(operation) for operation in change_set.operations}


def application_order(
    change_set: ChangeSet, *, beneath: Sequence[ChangeSet] = ()
) -> tuple[Operation, ...]:
    """The set's own operations in an order that applies: each after everything it needs.

    The operations of the sets *beneath* are not included — they are applied first, each as its own
    set — but they are what decide whether a reference this set does not create is resolvable at
    all. Refuses a set that names something nothing creates, and one whose operations need each
    other in a circle.
    """
    inherited = frozenset(alias for lower in beneath for alias in lower.created)
    unresolved = dangling(change_set.operations, inherited)
    if unresolved:
        raise MalformedChangeSet(
            f"the change set names {', '.join(unresolved)}, which neither it nor a set beneath it "
            "creates. Add the create, or name the entity by its id."
        )
    return ordered(change_set.by_claim, dependencies(change_set))


def ordered(
    by_claim: Mapping[OperationKey, Operation], needs: Dependencies
) -> tuple[Operation, ...]:
    """Operations in dependency order; among those free to go in any order, in canonical order."""
    sorter = TopologicalSorter({claim: needs.get(claim, frozenset()) for claim in by_claim})
    try:
        sorter.prepare()
    except CycleError as error:
        circle = " → ".join(str(claim) for claim in error.args[1])
        raise MalformedChangeSet(
            f"these operations each need another applied first, in a circle: {circle}. No order "
            "applies them."
        ) from error
    arranged: list[Operation] = []
    while sorter.is_active():
        ready = sorted((by_claim[claim] for claim in sorter.get_ready()), key=sort_key)
        arranged.extend(ready)
        sorter.done(*(operation.claim for operation in ready))
    return tuple(arranged)
