"""Recording an edit made to a candidate as one of its operations: merged per claim, with its base.

The canvas edits a candidate the way it edits a diagram — rename, details, create, connect, remove —
and each edit becomes an operation of the candidate. An editor states only what it wants; what the
operation was written against is read here, from what the candidate's stack beneath it says, because
that is the base the operation is later judged by and the client has no business computing it:

- **one operation per claim.** A second edit of the same field replaces the first; an edit that
  restores what the stack beneath says drops the operation, so typing a name back leaves nothing.
- **the base is the stack's**, read in the form the field's catalogue entry asks for: the value
  itself, or for prose and for a removal the revision of what is replaced (`base`).
- **what the candidate itself creates is edited in place.** Renaming an element the candidate
  created rewrites its create; removing it drops the create and everything that names it. An entity
  the candidate created is addressed by the id chosen for it, never by its alias, which is
  `provisional_reference`'s to spell.
- **so is what the stack beneath creates.** An edit, a removal or a connection naming the id a lower
  candidate's create chose is recorded under that create's alias, as the composition beneath names it
  (`created_names.reference_for`): a caller names an element the same way at every level of a stack.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, replace
from types import MappingProxyType
from typing import Any

from src.application.change_sets.base import (
    Base,
    BaseRevision,
    BaseValue,
    prose_revision,
    record_revision,
    says_the_same,
)
from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.composition import patched
from src.application.change_sets.created_names import ChosenIds, reference_for
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditConnection,
    EditEntity,
    MalformedChangeSet,
    Operation,
    OperationKey,
    RemoveConnection,
    RemoveEntity,
    entities_used,
)
from src.application.change_sets.reading import FieldValues, ModelReading
from src.application.modeling.edit_field_catalogue import KEYED, PROSE, ArtifactKind
from src.domain.artifact_id import MalformedArtifactIdError, canonical_entity_key, parse_entity_id

Intent = Mapping[str, Any]

#: What a candidate with nothing beneath it inherits: no create.
_NOTHING_CREATED_BENEATH: ChosenIds = MappingProxyType({})


def recorded(
    candidate: CandidateArchitecture, intent: Intent, beneath: ModelReading,
    created_beneath: ChosenIds = _NOTHING_CREATED_BENEATH,
) -> CandidateArchitecture:
    """*candidate* with *intent* recorded among its operations, read against *beneath*: the model with the stack
    beneath the candidate laid over, whose creates chose the ids in *created_beneath* (`chosen_ids`)."""
    if candidate.state != "draft":
        raise MalformedChangeSet(f"{candidate.name!r} is {candidate.state}; only a draft records new operations.")
    reader = _RECORDERS.get(str(intent.get("op", "")))
    if reader is None:
        edits = ", ".join(_RECORDERS)
        raise MalformedChangeSet(f"{intent.get('op')!r} is not an edit a candidate records. The edits are {edits}.")
    try:
        operations = reader(_Set(candidate.changes.operations, created_beneath), intent, beneath)
    except KeyError as missing:
        raise MalformedChangeSet(f"a {intent['op']} edit states its {missing.args[0]}") from missing
    return replace(candidate, changes=ChangeSet(operations, candidate.changes.repository_revision))


def rebased(
    candidate: CandidateArchitecture, operations: Iterable[Operation], beneath: ModelReading,
    created_beneath: ChosenIds = _NOTHING_CREATED_BENEATH,
) -> CandidateArchitecture:
    """*candidate* with each of *operations* recorded again against *beneath*, the model as it stands now.

    What a drifted operation's standing advises — make the edit again against the model as it is —
    done as one act: the value an edit asks for is kept and what it replaces is read again, so applying
    it overwrites deliberately what the model came to say. An edit the model has since come to agree
    with drops, as any edit back to its base does. Only what has a base can be re-based.
    """
    for operation in operations:
        candidate = recorded(candidate, _intent_of(operation), beneath, created_beneath)
    return candidate


def _intent_of(operation: Operation) -> Intent:
    """The edit that records *operation*: what it asks for, without what it was written against."""
    match operation:
        case EditEntity(target=target, field=field, value=value, key=key):
            return {"op": "edit_entity", "artifact_id": target, "field": field, "value": value, "key": key}
        case RemoveEntity(target=target):
            return {"op": "remove_entity", "artifact_id": target}
        case EditConnection(address=address, field=field, value=value, key=key):
            return {"op": "edit_connection", **asdict(address), "field": field, "value": value, "key": key}
        case RemoveConnection(address=address):
            return {"op": "remove_connection", **asdict(address)}
        case _:
            raise MalformedChangeSet("A create or an add states all it makes, so it has no base to re-read.")


class _Set:
    """The candidate's operations while one edit is recorded among them."""

    def __init__(self, operations: tuple[Operation, ...], created_beneath: ChosenIds) -> None:
        self.operations = operations
        self.created_beneath = created_beneath
        creates = [op for op in operations if isinstance(op, CreateEntity)]
        self.created = {
            **{op.reference: op for op in creates},
            **{canonical_entity_key(op.artifact_id): op for op in creates if op.artifact_id},
        }
        self.added = {op.address: op for op in operations if isinstance(op, AddConnection)}

    def reference(self, named: str) -> str:
        """How the set names *named*: the alias of what it or the stack beneath creates, else the id as named."""
        create = self.creating(named)
        return create.reference if create else reference_for(named, self.created_beneath)

    def creating(self, named: str) -> CreateEntity | None:
        """The create of this set that *named* names: by the id it chose, in either spelling, or by its alias."""
        return self.created.get(canonical_entity_key(named))

    def kept(self, operations: tuple[Operation, ...]) -> _Set:
        return _Set(operations, self.created_beneath)

    def address(self, intent: Intent) -> ConnectionAddress:
        return ConnectionAddress(
            self.reference(str(intent["source_entity"])), str(intent["connection_type"]),
            self.reference(str(intent["target_entity"])),
        )

    def without(self, drop: Callable[[Operation], bool]) -> tuple[Operation, ...]:
        return tuple(op for op in self.operations if not drop(op))

    def put(self, operation: Operation) -> tuple[Operation, ...]:
        """The set with *operation* in place of whatever held its claim."""
        return (*self.without(lambda op: op.claim == operation.claim), operation)

    def dropping(self, claim: OperationKey) -> tuple[Operation, ...]:
        return self.without(lambda op: op.claim == claim)


def _key(intent: Intent) -> str | None:
    key = intent.get("key")
    return None if key is None else str(key)


def _held(kind: ArtifactKind, values: FieldValues, field: str, key: str | None) -> Any:
    """What *values* holds of the field an edit names: the one key of a keyed field, or the field."""
    held = values.get(field)
    return held.get(key) if field in KEYED[kind] and isinstance(held, Mapping) else held


def _base(kind: ArtifactKind, field: str, value: Any) -> Base:
    return BaseRevision(prose_revision(value)) if field in PROSE[kind] else BaseValue(value)


def _create_entity(held: _Set, intent: Intent, _: ModelReading) -> tuple[Operation, ...]:
    chosen = str(intent["artifact_id"])
    try:
        stable = parse_entity_id(chosen)
    except MalformedArtifactIdError as refusal:
        raise MalformedChangeSet(f"{chosen!r} is not an artifact id a new entity can be given: {refusal}") from refusal
    earlier = held.creating(chosen)
    alias = earlier.ref if earlier else f"{stable.epoch}-{stable.random}"
    return held.put(CreateEntity(ref=alias, fields=dict(intent["fields"]), artifact_id=chosen))


def _edit_entity(held: _Set, intent: Intent, beneath: ModelReading) -> tuple[Operation, ...]:
    named, field, key, value = str(intent["artifact_id"]), str(intent["field"]), _key(intent), intent.get("value")
    create = held.creating(named)
    if create is not None:
        edit = EditEntity(target=create.reference, field=field, value=value, base=_base("entity", field, None), key=key)
        return held.put(replace(create, fields=patched("entity", create.fields, edit)))
    target = held.reference(named)
    current = beneath.entity(target)
    if current is None:
        raise MalformedChangeSet(f"{named!r} is not an entity this candidate can see, so it cannot be edited here.")
    was = _held("entity", current, field, key)
    base = _base("entity", field, was)
    edit = EditEntity(target=target, field=field, value=value, base=base, key=key)
    return held.dropping(edit.claim) if says_the_same(base, was, value) else held.put(edit)


def _remove_entity(held: _Set, intent: Intent, beneath: ModelReading) -> tuple[Operation, ...]:
    named = str(intent["artifact_id"])
    create = held.creating(named)
    if create is not None:
        return held.without(lambda op: op is create or create.reference in entities_used(op))
    target = held.reference(named)
    current = beneath.entity(target)
    if current is None:
        raise MalformedChangeSet(f"{named!r} is not an entity this candidate can see, so it cannot be removed here.")
    kept = held.without(lambda op: isinstance(op, EditEntity) and op.target == canonical_entity_key(target))
    return held.kept(kept).put(RemoveEntity(target=target, base=BaseRevision(record_revision(current))))


def _add_connection(held: _Set, intent: Intent, _: ModelReading) -> tuple[Operation, ...]:
    return held.put(AddConnection(address=held.address(intent), fields=dict(intent.get("fields") or {})))


def _edit_connection(held: _Set, intent: Intent, beneath: ModelReading) -> tuple[Operation, ...]:
    address, field, key, value = held.address(intent), str(intent["field"]), _key(intent), intent.get("value")
    added = held.added.get(address)
    if added is not None:
        edit = EditConnection(address=address, field=field, value=value, base=_base("connection", field, None), key=key)
        return held.put(replace(added, fields=patched("connection", added.fields, edit)))
    current = beneath.connection(address)
    if current is None:
        raise MalformedChangeSet(f"{address} is not a connection this candidate can see, so it cannot be edited here.")
    was = _held("connection", current, field, key)
    base = _base("connection", field, was)
    edit = EditConnection(address=address, field=field, value=value, base=base, key=key)
    return held.dropping(edit.claim) if says_the_same(base, was, value) else held.put(edit)


def _remove_connection(held: _Set, intent: Intent, beneath: ModelReading) -> tuple[Operation, ...]:
    address = held.address(intent)
    if address in held.added:
        return held.without(lambda op: isinstance(op, AddConnection | EditConnection) and op.address == address)
    current = beneath.connection(address)
    if current is None:
        raise MalformedChangeSet(f"{address} is not a connection this candidate can see, so it cannot be removed here.")
    kept = held.without(lambda op: isinstance(op, EditConnection) and op.address == address)
    return held.kept(kept).put(RemoveConnection(address=address, base=BaseRevision(record_revision(current))))


def _drop(held: _Set, intent: Intent, _: ModelReading) -> tuple[Operation, ...]:
    """Take back what the set records about one entity or connection — or about one field of it.

    Dropping what the set creates drops the create and everything that names it, as removing it does.
    Nothing recorded about it is a refusal: a drop that takes back nothing is a mistaken address.
    """
    field, key = intent.get("field"), _key(intent)
    if intent.get("artifact_id"):
        create = held.creating(str(intent["artifact_id"]))
        if create is not None and field is None:
            return held.without(lambda op: op is create or create.reference in entities_used(op))
        subject: str | ConnectionAddress = canonical_entity_key(held.reference(str(intent["artifact_id"])))
    else:
        subject = held.address(intent)

    def taken(op: Operation) -> bool:
        claim = op.claim
        return claim.subject == subject and (field is None or (claim.field == field and claim.key == (key or "")))

    kept = held.without(taken)
    if len(kept) == len(held.operations):
        what = f"{field} of {subject}" if field else str(subject)
        raise MalformedChangeSet(f"This candidate records nothing about {what}, so there is nothing to drop.")
    return kept


#: One recorder per edit. The six are the operations a change set is made of; `drop` takes one back.
_RECORDERS: Mapping[str, Callable[[_Set, Intent, ModelReading], tuple[Operation, ...]]] = {
    "create_entity": _create_entity,
    "edit_entity": _edit_entity,
    "remove_entity": _remove_entity,
    "add_connection": _add_connection,
    "edit_connection": _edit_connection,
    "remove_connection": _remove_connection,
    "drop": _drop,
}
