"""Where several change sets touch the same thing — found from the operations alone.

Two classes, both decidable without reading the model:

* **same key** — two sets change one key. Where they ask for the same value the sets *converge*:
  applying both is applying either, and nothing needs deciding. Where they differ, someone has to
  choose.
* **remove versus use** — one set removes an entity or a connection that another edits or connects
  to. Neither is wrong alone; together one of them is.

**The detector is the submission's, over a finer key.** `contested` answers "who else claims this"
for proposed changes by (artifact, field) and here by (subject, field, key). A submission refuses on
sight; sets compare values first, which is the only difference and is decided here.

**Sets are named by the caller.** A change set has no identity of its own, so the sets arrive under
whatever names their holder gives them — candidate ids, proposal ids — and every party is reported
under that name.

**A set and the set it is read on top of do not overlap.** An upper set that changes what the lower
one changes is what stacking *is*: its value is the stack's. `stacked_on` says which set is read on
top of which, and a party whose set lies beneath another party's is not counted against it.

**An alias belongs to the set that creates it.** `$ref:queue` in one set and `$ref:queue` in an
unrelated one are two entities that happen to share a name, so every reference is read in the scope
of the set that owns it — the set itself, or the one beneath it whose entity it is.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias

from src.application.change_sets.change_set import ChangeSet
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
from src.application.modeling.edit_field_values import comparable
from src.domain.provisional_reference import alias_of

#: How two sets touch the same thing.
OverlapKind: TypeAlias = Literal["same-key", "remove-versus-use"]


@dataclass(frozen=True, slots=True)
class Party:
    """One side of an overlap: a set, by the name its holder gave it, and the operation involved."""

    set_id: str
    operation: Operation


@dataclass(frozen=True, slots=True)
class Overlap:
    """One thing more than one set touches, and every operation that touches it."""

    kind: OverlapKind
    #: What is contested, in words: the key, or the thing removed.
    subject: str
    parties: tuple[Party, ...]
    #: Every party asks for the same thing, so applying all of them is applying any one.
    convergent: bool = False


@dataclass(frozen=True, slots=True)
class _Scoped:
    """One named set among the others: which it is, and which set it is read on top of."""

    name: str
    change_set: ChangeSet
    beneath: str | None

    def is_stacked_with(self, other: _Scoped) -> bool:
        return self.beneath == other.name or other.beneath == self.name

    def owner_of(self, reference: str) -> tuple[str | None, str]:
        """A reference, with the set whose entity it names where the reference is provisional."""
        if alias_of(reference) is None:
            return (None, reference)
        return (self.name if reference in self.change_set.created else self.beneath, reference)


def overlaps(
    sets: Mapping[str, ChangeSet], *, stacked_on: Mapping[str, str] | None = None
) -> tuple[Overlap, ...]:
    """Every overlap between *sets*: same-key first, then remove-versus-use, each in a stable order.

    `stacked_on` names, for a set read on top of another, the set beneath it.
    """
    below = stacked_on or {}
    scoped = [_Scoped(name, change_set, below.get(name)) for name, change_set in sets.items()]
    parties = [(owner, Party(owner.name, op)) for owner in scoped for op in owner.change_set.operations]
    return (*_same_key(parties), *_remove_versus_use(parties))


def conflicts(
    sets: Mapping[str, ChangeSet], *, stacked_on: Mapping[str, str] | None = None
) -> tuple[Overlap, ...]:
    """The overlaps that need a decision: everything that does not converge."""
    return tuple(o for o in overlaps(sets, stacked_on=stacked_on) if not o.convergent)


def _same_key(parties: Sequence[tuple[_Scoped, Party]]) -> list[Overlap]:
    beneath_of = {owner.name: owner.beneath for owner, _ in parties}
    claims = ((_scoped_claim(owner, party.operation), party) for owner, party in parties)
    found: list[Overlap] = []
    for claimants in contested(claims).values():
        overlaid = {beneath_of[party.set_id] for party in claimants}
        topmost = tuple(party for party in claimants if party.set_id not in overlaid)
        if len(topmost) > 1:
            effects = {_effect(party.operation) for party in topmost}
            found.append(
                Overlap("same-key", str(topmost[0].operation.claim), topmost, len(effects) == 1)
            )
    return found


def _remove_versus_use(parties: Sequence[tuple[_Scoped, Party]]) -> list[Overlap]:
    found: list[Overlap] = []
    for owner, remover in parties:
        removed = _scoped_removal(owner, remover.operation)
        if removed is None:
            continue
        users = tuple(
            user
            for other, user in parties
            if other.name != owner.name
            and not owner.is_stacked_with(other)
            and removed in _scoped_uses(other, user.operation)
        )
        if users:
            found.append(
                Overlap("remove-versus-use", str(remover.operation.claim), (remover, *users))
            )
    return found


def _scoped_subject(owner: _Scoped, subject: str | ConnectionAddress) -> Hashable:
    if isinstance(subject, str):
        return owner.owner_of(subject)
    return (
        owner.owner_of(subject.source_entity),
        subject.connection_type,
        owner.owner_of(subject.target_entity),
    )


def _scoped_claim(owner: _Scoped, operation: Operation) -> Hashable:
    claim = operation.claim
    return (claim.kind, _scoped_subject(owner, claim.subject), claim.field, claim.key)


def _scoped_removal(owner: _Scoped, operation: Operation) -> Hashable | None:
    """What a removal removes, or None for an operation that removes nothing."""
    match operation:
        case RemoveEntity(target=target):
            return _scoped_subject(owner, target)
        case RemoveConnection(address=address):
            return _scoped_subject(owner, address)
        case _:
            return None


def _scoped_uses(owner: _Scoped, operation: Operation) -> frozenset[Hashable]:
    """Everything an operation needs to exist: the entities it uses, and a connection it edits."""
    used: set[Hashable] = {_scoped_subject(owner, entity) for entity in entities_used(operation)}
    if isinstance(operation, EditConnection):
        used.add(_scoped_subject(owner, operation.address))
    return frozenset(used)


def _effect(operation: Operation) -> Hashable:
    """What an operation asks for, apart from what it was written against and any note on it.

    Two operations with the same effect converge even if they recorded different bases: they were
    written at different times and want the same model.
    """
    match operation:
        case CreateEntity(fields=fields, artifact_id=artifact_id):
            return ("states", _hashable(fields), artifact_id)
        case AddConnection(fields=fields):
            return ("states", _hashable(fields))
        case EditEntity(value=value) | EditConnection(value=value):
            return ("value", _hashable(value))
        case RemoveEntity() | RemoveConnection():
            return ("removed",)


def _hashable(value: object) -> Hashable:
    """A value in the form two readings of the same content share, and that a set can hold."""
    return repr(comparable(value))
