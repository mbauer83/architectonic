"""Splitting one change set in two, and merging two into one — without cutting a dependency.

Both are rearrangements of operations between sets, and both have the same way to go wrong: an
operation ends up in a set that no longer contains what it needs. A connection to an entity the set
creates, moved away from that create, names an alias nothing in its new set defines. So both refuse
rather than repair: which side the create belongs on is the author's decision, and a split that
quietly dragged it along would produce two sets nobody asked for.

Stated over the operations alone. Whether the sets being rearranged *may* be — a candidate
architecture that has been offered may not — is a question about their holder, asked there
(`candidate_work`).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import replace

from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.coherence import provisional_uses
from src.application.change_sets.operations import MalformedChangeSet, OperationKey
from src.application.change_sets.ordering import dependencies
from src.application.change_sets.overlap import conflicts, overlaps

#: The names the two sets of a merge are compared under. A change set has none of its own.
_FIRST, _SECOND = "the first set", "the second set"


def split(change_set: ChangeSet, moved: Collection[OperationKey]) -> tuple[ChangeSet, ChangeSet]:
    """*change_set* without the operations *moved* names, and a second set holding them.

    Both are written against the revision the original was. Refuses to move an operation the set
    does not have, and to separate an operation from one it needs.
    """
    by_claim = change_set.by_claim
    unknown = sorted(str(claim) for claim in moved if claim not in by_claim)
    if unknown:
        raise MalformedChangeSet(
            f"the change set has no operation changing {', '.join(unknown)}, so there is nothing "
            "there to move."
        )
    for claim, needed in dependencies(change_set).items():
        for prerequisite in sorted(needed, key=str):
            if (claim in moved) != (prerequisite in moved):
                raise MalformedChangeSet(
                    f"the operation changing {claim} needs the one changing {prerequisite}, and "
                    "this split would put them in different sets. Move both, or neither."
                )
    staying = tuple(op for op in change_set.operations if op.claim not in moved)
    leaving = tuple(op for op in change_set.operations if op.claim in moved)
    return (replace(change_set, operations=staying), replace(change_set, operations=leaving))


def merge(first: ChangeSet, second: ChangeSet) -> ChangeSet:
    """One set holding the operations of both. Operations that converge are kept once.

    The two are taken to be read on top of the same thing; a caller whose sets are not refuses
    before asking.
    """
    if first.repository_revision != second.repository_revision:
        raise MalformedChangeSet(
            f"one set was written against revision {first.repository_revision} and the other "
            f"against {second.repository_revision}. A merged set records one revision; bring the "
            "older set up to the newer revision first."
        )
    _refuse_captured_aliases(first, second)
    both = {_FIRST: first, _SECOND: second}
    disputed = conflicts(both)
    if disputed:
        raise MalformedChangeSet(
            f"the two sets disagree about {disputed[0].subject}"
            + (f" and {len(disputed) - 1} more" if len(disputed) > 1 else "")
            + ". Merging would have to choose between them; settle each in one of the sets first."
        )
    duplicated = {
        party.operation.claim
        for overlap in overlaps(both)
        for party in overlap.parties
        if party.set_id == _SECOND
    }
    return replace(
        first,
        operations=(
            *first.operations,
            *(op for op in second.operations if op.claim not in duplicated),
        ),
    )


def _refuse_captured_aliases(first: ChangeSet, second: ChangeSet) -> None:
    """Refuse a merge in which an alias would come to mean a different entity.

    Two creates under one alias collide outright. Subtler: a set that names `$ref:x` from the set
    beneath it, merged with a set that creates its own `$ref:x`, would have its reference silently
    rebound.
    """
    both = sorted(set(first.created) & set(second.created))
    if both:
        raise MalformedChangeSet(
            f"the two sets each create an entity called {', '.join(both)}. In one set an alias "
            "names one entity: rename one of them before merging."
        )
    for user, creator in ((first, second), (second, first)):
        captured = sorted(
            (provisional_uses(user.operations) - set(user.created)) & set(creator.created)
        )
        if captured:
            raise MalformedChangeSet(
                f"one set names {', '.join(captured)} from the set beneath it, and the other "
                "creates an entity under the same alias. Merged, the reference would mean the new "
                "entity instead: rename the alias before merging."
            )
