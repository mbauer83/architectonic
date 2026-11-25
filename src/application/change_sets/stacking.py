"""Which candidates a candidate is read on top of: its stack, from the lowest up.

A candidate names one parent; the parent may name its own. The stack is that chain read down to a
candidate with no parent, and it may be any depth: a naive architecture started from an existing
candidate, adaptations of the naive, a candidate built on an adaptation. Three things make a chain
unreadable, and each is refused with what to do:

* a parent that is not there — the candidate cannot be read without what it was written on;
* a circle — no candidate in it is the lowest, so there is nothing to apply first;
* an alias created twice in one stack — `$ref:queue` would name two entities, and an upper layer's
  reference could not say which.

**What may be compared with what** follows from the stack too. A candidate's diff is read against a
base that is not itself and not one of the candidates stacked on it (`descendants`): against those,
a candidate's own operations would be the base's.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable

from src.application.change_sets.candidate_architecture import (
    CandidateArchitecture,
    MalformedCandidateArchitecture,
)
from src.application.change_sets.change_set import ChangeSet

#: The candidate with an id, or None where there is none.
FindCandidate = Callable[[str], CandidateArchitecture | None]


def stack_of(candidate: CandidateArchitecture, find: FindCandidate) -> tuple[CandidateArchitecture, ...]:
    """*candidate* and every candidate beneath it, lowest first. Refuses an unreadable chain."""
    chain = [candidate]
    seen = {candidate.id}
    while (parent_id := chain[-1].parent_id) is not None:
        if parent_id in seen:
            circle = " → ".join([*(held.id for held in chain), parent_id])
            raise MalformedCandidateArchitecture(
                f"these candidates are stacked on each other in a circle: {circle}. Give one of them "
                "no parent, or a parent outside the circle."
            )
        parent = find(parent_id)
        if parent is None:
            raise MalformedCandidateArchitecture(
                f"'{chain[-1].id}' is read on top of '{parent_id}', which does not exist. A "
                "candidate cannot be read without the one beneath it: restore it, or re-stack "
                f"'{chain[-1].id}' on another."
            )
        seen.add(parent.id)
        chain.append(parent)
    stack = tuple(reversed(chain))
    _refuse_reused_aliases(stack)
    return stack


def sets_beneath(stack: tuple[CandidateArchitecture, ...]) -> tuple[ChangeSet, ...]:
    """The change sets under the top of *stack*, lowest first — what `compose` takes as `beneath`."""
    return tuple(layer.changes for layer in stack[:-1])


def descendants(candidate_id: str, candidates: Iterable[CandidateArchitecture]) -> frozenset[str]:
    """The ids of every candidate stacked, at any depth, on the one called *candidate_id*."""
    children: dict[str, list[str]] = {}
    for held in candidates:
        if held.parent_id is not None:
            children.setdefault(held.parent_id, []).append(held.id)
    found: set[str] = set()
    waiting = list(children.get(candidate_id, ()))
    while waiting:
        child = waiting.pop()
        if child not in found:
            found.add(child)
            waiting.extend(children.get(child, ()))
    return frozenset(found)


def _refuse_reused_aliases(stack: tuple[CandidateArchitecture, ...]) -> None:
    counted = Counter(alias for layer in stack for alias in layer.changes.created)
    reused = sorted(alias for alias, times in counted.items() if times > 1)
    if reused:
        raise MalformedCandidateArchitecture(
            f"{', '.join(reused)} {'is' if len(reused) == 1 else 'are'} created by more than one "
            "candidate in one stack, so a reference to it could not say which entity it means. "
            "Give the upper candidate's create another alias."
        )


def drawn_on(stack: tuple[CandidateArchitecture, ...]) -> str | None:
    """The stored diagram the top of *stack* is drawn on: the nearest one a layer names, top first."""
    return next((layer.diagram for layer in reversed(stack) if layer.diagram), None)
