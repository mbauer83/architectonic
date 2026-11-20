"""Whether a set's operations can stand together: one per claim, and none contradicting another.

Checked when the set is built, because every contradiction here has the same shape — two operations
whose combined meaning depends on which is applied first — and a change set has no authored order to
settle it with. Order is derived from what the operations refer to; where that leaves two operations
unordered and they disagree, the set says nothing definite and is refused.

Each check answers with the sentence to refuse with, or `None`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import chain

from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditConnection,
    EditEntity,
    Operation,
    RemoveConnection,
    RemoveEntity,
    entities_used,
)
from src.application.modeling.claim_overlap import contested
from src.domain.provisional_reference import alias_of

#: One check over a set's operations: the refusal, or None.
Check = Callable[[Sequence[Operation]], str | None]


def created_by(operations: Iterable[Operation]) -> Mapping[str, CreateEntity]:
    """The entities these operations create, by the reference the rest of the set names them with."""
    return {op.reference: op for op in operations if isinstance(op, CreateEntity)}


def provisional_uses(operations: Iterable[Operation]) -> frozenset[str]:
    """Every provisional reference these operations name, whoever is meant to create it."""
    named = chain.from_iterable(_entities_named(op) for op in operations)
    return frozenset(reference for reference in named if alias_of(reference) is not None)


def _entities_named(operation: Operation) -> tuple[str, ...]:
    """Every entity an operation mentions — those it needs, and those it removes or disconnects."""
    match operation:
        case RemoveEntity(target=target):
            return (target,)
        case RemoveConnection(address=address):
            return address.endpoints
        case _:
            return entities_used(operation)


def _one_operation_per_claim(operations: Sequence[Operation]) -> str | None:
    claims = ((op.claim, index) for index, op in enumerate(operations))
    for claim in contested(claims):
        return (
            f"two operations change {claim}. A set holds one operation per key: with no authored "
            "order, whichever applied second would silently win. Keep the one that says what the "
            "set means."
        )
    return None


def _a_create_says_everything(operations: Sequence[Operation]) -> str | None:
    """Nothing else in the set edits what the set itself creates, or names it by a chosen id.

    Removing it needs no rule of its own: a create and a removal claim the same entity whole.
    """
    created = created_by(operations)
    chosen_ids = {op.artifact_id: op for op in created.values() if op.artifact_id}
    for op in operations:
        if isinstance(op, EditEntity) and op.target in created:
            return (
                f"{op.claim} is changed by an operation of its own, and the same set creates "
                f"{op.target}. A create states everything about what it creates: put the value in "
                "the create, or leave the entity out."
            )
        for entity in _entities_named(op):
            if entity in chosen_ids:
                return (
                    f"an operation names {entity} by its id, and the same set creates it as "
                    f"{chosen_ids[entity].reference}. Inside the set an entity it creates is named "
                    "by its alias."
                )
    return None


def _an_add_says_everything(operations: Sequence[Operation]) -> str | None:
    """Nothing else in the set edits a connection the set itself adds."""
    added = {op.address for op in operations if isinstance(op, AddConnection)}
    for op in operations:
        if isinstance(op, EditConnection) and op.address in added:
            return (
                f"{op.claim} is changed by an operation of its own, and the same set adds that "
                "connection. Put the value in the operation that adds it."
            )
    return None


def _nothing_removed_is_used(operations: Sequence[Operation]) -> str | None:
    """A set does not remove an entity or a connection that another of its operations needs."""
    removed_entities = {op.target for op in operations if isinstance(op, RemoveEntity)}
    removed: set[ConnectionAddress] = {
        op.address for op in operations if isinstance(op, RemoveConnection)
    }
    for op in operations:
        for entity in entities_used(op):
            if entity in removed_entities:
                return (
                    f"the set removes {entity} and also changes {op.claim}, which needs it. One "
                    "of the two is not meant: a removal and a use of the same entity have no "
                    "order in which both hold."
                )
        if isinstance(op, EditConnection) and op.address in removed:
            return (
                f"the set removes the connection {op.address} and also changes {op.claim}. One of "
                "the two is not meant."
            )
    return None


#: Every check a set's operations pass, in the order an author would want to hear about them.
CHECKS: tuple[Check, ...] = (
    _one_operation_per_claim,
    _a_create_says_everything,
    _an_add_says_everything,
    _nothing_removed_is_used,
)


def first_refusal(operations: Sequence[Operation]) -> str | None:
    """Why these operations cannot stand together, or None when they can."""
    return next((refusal for check in CHECKS if (refusal := check(operations)) is not None), None)


def dangling(operations: Sequence[Operation], also_created: frozenset[str]) -> tuple[str, ...]:
    """The provisional references these operations name that nothing creates."""
    created = frozenset(created_by(operations)) | also_created
    return tuple(sorted(provisional_uses(operations) - created))
