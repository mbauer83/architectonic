"""Integrating candidates: a new candidate holding the chosen candidates' operations, their conflicts resolved.

Plan §3 and the candidate decision: chosen candidates are integrated into a new candidate that holds what
each proposes. Where two of them claim the same thing differently, or one removes what another uses, the
author decides, one conflict at a time, and each decision is one of the actions a conflict permits:

* **take** one party's side — its operation stays, the other parties' operations on that subject go;
* **drop** one party's operation — the others stay, and if two of them still disagree, that remains;
* **merge** — for parties that each set the same field (or key) to a different value, a value of the
  author's own written into the integration in their place.

Raising a decision is not an action here: it records nothing in the integration, and the conflict stays
until one of the three settles it.

**Resolutions are applied in order, each over what the ones before left.** The conflicts are found again
after every one (`overlap.conflicts`, the one detector the overlap check also answers with), so a drop
among three parties leaves the two that still disagree as a conflict of their own, to be settled by the
next resolution. A resolution names its conflict by kind and subject, as the check reports it; one that
names no conflict standing at that point is refused, so a stale list of resolutions cannot settle a
conflict it never saw.

**The integration is a draft on the parent the candidates share**, and holds every operation of every
candidate that is left, converging ones once (`partition.merge`). Candidates written at different times
recorded different repository revisions; the revision is a stamp and drift is decided per operation by
its base (owner decision D6), so the integration records the revision it is made at. The candidates
themselves are not changed: what becomes of them is their author's next decision.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import reduce
from typing import Literal, TypeAlias, get_args

from src.application.change_sets import partition
from src.application.change_sets.candidate_apply import TERMINAL
from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import EditConnection, EditEntity, Operation
from src.application.change_sets.overlap import Overlap, OverlapKind, conflicts

#: What may be done about a conflict.
ResolutionAction: TypeAlias = Literal["take", "drop", "merge"]
RESOLUTION_ACTIONS: tuple[ResolutionAction, ...] = get_args(ResolutionAction)


class UnresolvableIntegration(ValueError):
    """Integration asked of candidates that cannot be integrated, or resolved as they cannot be. Says why."""


@dataclass(frozen=True, slots=True)
class Resolution:
    """One conflict, by kind and subject as the check reports it, and what is done about it."""

    kind: OverlapKind
    subject: str
    action: ResolutionAction
    #: The candidate whose side is taken, or whose operation is dropped.
    party: str | None = None
    #: The merged value, for `merge`.
    value: object = None


@dataclass(frozen=True, slots=True)
class Conflict:
    """An overlap that needs a decision, and the actions it permits."""

    overlap: Overlap
    actions: tuple[ResolutionAction, ...]


@dataclass(frozen=True, slots=True)
class Integration:
    """The new candidate, or — while a conflict stands — none, and the conflicts still to settle."""

    candidate: CandidateArchitecture | None
    conflicts: tuple[Conflict, ...]
    #: How many operations the integration holds, or would once its conflicts are settled.
    operations: int


def permitted(overlap: Overlap) -> tuple[ResolutionAction, ...]:
    """The actions *overlap* permits: a merged value only where every party sets a value of one field."""
    sets_a_value = all(isinstance(party.operation, EditEntity | EditConnection) for party in overlap.parties)
    merges = overlap.kind == "same-key" and sets_a_value
    return ("take", "drop", "merge") if merges else ("take", "drop")


def integrate(
    candidates: Sequence[CandidateArchitecture], resolutions: Sequence[Resolution], *,
    id: str,  # noqa: A002 — the integration's id, named as the value names it
    name: str, rationale: str, revision: str,
) -> Integration:
    """*candidates* integrated into a new draft named *name*, with *resolutions* applied in order.

    Refuses fewer than two candidates, a final one, candidates on different parents, and a resolution that
    names no standing conflict or an action, party or value its conflict does not permit.
    """
    parent = _common_parent(candidates)
    sets = reduce(_resolved, resolutions, {one.id: one.changes for one in candidates})
    standing = conflicts(sets)
    merged = _merged(tuple(sets.values()), revision) if not standing else None
    count = len(merged.operations) if merged else len({op.claim for one in sets.values() for op in one.operations})
    if merged is None:
        return Integration(None, tuple(Conflict(one, permitted(one)) for one in standing), count)
    return Integration(CandidateArchitecture(
        id=id, name=name, rationale=rationale, state="draft", changes=merged, parent_id=parent,
        answers=_union(one.answers for one in candidates), satisfies=_union(one.satisfies for one in candidates),
        scope=_union(one.scope for one in candidates),
    ), (), count)


def _common_parent(candidates: Sequence[CandidateArchitecture]) -> str | None:
    if len({one.id for one in candidates}) < 2 or len(candidates) != len({one.id for one in candidates}):
        raise UnresolvableIntegration("Choose two or more distinct candidates to integrate.")
    final = [f"{one.id} ({one.state})" for one in candidates if one.state in TERMINAL]
    if final:
        raise UnresolvableIntegration(
            f"{', '.join(final)} {'is' if len(final) == 1 else 'are'} final; only drafts and offered candidates "
            "are integrated."
        )
    parents = {one.parent_id for one in candidates}
    if len(parents) > 1:
        named = ", ".join(f"{one.id} on {one.parent_id or 'the model'}" for one in candidates)
        raise UnresolvableIntegration(
            f"The candidates are read on top of different candidates ({named}), so one integration could not be "
            "read on top of all of them. Integrate candidates that stack on the same one."
        )
    return parents.pop()


def _resolved(sets: Mapping[str, ChangeSet], resolution: Resolution) -> dict[str, ChangeSet]:
    """*sets* with *resolution* applied to the conflict it names, as the conflicts stand now."""
    standing = conflicts(sets)
    conflict = next(
        (one for one in standing if (one.kind, one.subject) == (resolution.kind, resolution.subject)), None,
    )
    if conflict is None:
        raise UnresolvableIntegration(
            f"No {resolution.kind} conflict about {resolution.subject} stands between the candidates now; check "
            "them again and resolve what the check reports."
        )
    if resolution.action not in permitted(conflict):
        raise UnresolvableIntegration(
            f"The {conflict.kind} conflict about {conflict.subject} permits {', '.join(permitted(conflict))}, "
            f"not {resolution.action}."
        )
    parties = {party.set_id for party in conflict.parties}
    if resolution.action != "merge" and resolution.party not in parties:
        raise UnresolvableIntegration(
            f"To {resolution.action} in the conflict about {conflict.subject}, name one of its parties: "
            f"{', '.join(sorted(parties))}."
        )
    return {name: ChangeSet(_kept(name, changes, conflict, resolution), changes.repository_revision)
            for name, changes in sets.items()}


def _kept(name: str, changes: ChangeSet, conflict: Overlap, resolution: Resolution) -> tuple[Operation, ...]:
    """*name*'s operations once *resolution* has settled *conflict*."""
    involved = {party.operation for party in conflict.parties if party.set_id == name}
    first = conflict.parties[0]
    rewrite: Callable[[Operation], Operation | None] = {
        "take": lambda op: op if name == resolution.party or op not in involved else None,
        "drop": lambda op: None if name == resolution.party and op in involved else op,
        "merge": lambda op: op if op not in involved else (
            _with_value(op, resolution.value) if name == first.set_id and op == first.operation else None
        ),
    }[resolution.action]
    return tuple(kept for op in changes.operations if (kept := rewrite(op)) is not None)


def _with_value(operation: Operation, value: object) -> Operation:
    if not isinstance(operation, EditEntity | EditConnection):
        raise UnresolvableIntegration("Only an edit that sets a value can take a merged value.")
    return replace(operation, value=value)


def _merged(sets: tuple[ChangeSet, ...], revision: str) -> ChangeSet:
    """One set holding every operation of *sets*, converging ones once, recorded at *revision*."""
    stamped = [ChangeSet(one.operations, revision) for one in sets]
    return reduce(partition.merge, stamped[1:], stamped[0])


def _union(groups: Iterable[Iterable[str]]) -> tuple[str, ...]:
    """Every reference in *groups*, in order, each once."""
    return tuple(dict.fromkeys(ref for group in groups for ref in group))
