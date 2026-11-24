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
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, replace
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

Intent = Mapping[str, Any]


def recorded(candidate: CandidateArchitecture, intent: Intent, beneath: ModelReading) -> CandidateArchitecture:
    """*candidate* with *intent* recorded among its operations, read against *beneath*."""
    if candidate.state != "draft":
        raise MalformedChangeSet(f"{candidate.name!r} is {candidate.state}; only a draft records new operations.")
    reader = _RECORDERS.get(str(intent.get("op", "")))
    if reader is None:
        edits = ", ".join(_RECORDERS)
        raise MalformedChangeSet(f"{intent.get('op')!r} is not an edit a candidate records. The edits are {edits}.")
    try:
        operations = reader(_Set(candidate.changes.operations), intent, beneath)
    except KeyError as missing:
        raise MalformedChangeSet(f"a {intent['op']} edit states its {missing.args[0]}") from missing
    return replace(candidate, changes=ChangeSet(operations, candidate.changes.repository_revision))


def rebased(
    candidate: CandidateArchitecture, operations: Iterable[Operation], beneath: ModelReading,
) -> CandidateArchitecture:
    """*candidate* with each of *operations* recorded again against *beneath*, the model as it stands now.

    What a drifted operation's standing advises — make the edit again against the model as it is —
    done as one act: the value an edit asks for is kept and what it replaces is read again, so applying
    it overwrites deliberately what the model came to say. An edit the model has since come to agree
    with drops, as any edit back to its base does. Only what has a base can be re-based.
    """
    for operation in operations:
        candidate = recorded(candidate, _intent_of(operation), beneath)
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

    def __init__(self, operations: tuple[Operation, ...]) -> None:
        self.operations = operations
        self.created = {op.artifact_id: op for op in operations if isinstance(op, CreateEntity) and op.artifact_id}
        self.added = {op.address: op for op in operations if isinstance(op, AddConnection)}

    def reference(self, artifact_id: str) -> str:
        """How the set names *artifact_id*: the alias of what it creates, else the id."""
        create = self.created.get(artifact_id)
        return create.reference if create else artifact_id

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
    alias = chosen.split("@", 1)[-1].replace(".", "-")
    return held.put(CreateEntity(ref=alias, fields=dict(intent["fields"]), artifact_id=chosen))


def _edit_entity(held: _Set, intent: Intent, beneath: ModelReading) -> tuple[Operation, ...]:
    target, field, key, value = str(intent["artifact_id"]), str(intent["field"]), _key(intent), intent.get("value")
    create = held.created.get(target)
    if create is not None:
        edit = EditEntity(target=create.reference, field=field, value=value, base=_base("entity", field, None), key=key)
        return held.put(replace(create, fields=patched("entity", create.fields, edit)))
    current = beneath.entity(target)
    if current is None:
        raise MalformedChangeSet(f"{target!r} is not an entity this candidate can see, so it cannot be edited here.")
    was = _held("entity", current, field, key)
    base = _base("entity", field, was)
    edit = EditEntity(target=target, field=field, value=value, base=base, key=key)
    return held.dropping(edit.claim) if says_the_same(base, was, value) else held.put(edit)


def _remove_entity(held: _Set, intent: Intent, beneath: ModelReading) -> tuple[Operation, ...]:
    target = str(intent["artifact_id"])
    create = held.created.get(target)
    if create is not None:
        return held.without(lambda op: op is create or create.reference in entities_used(op))
    current = beneath.entity(target)
    if current is None:
        raise MalformedChangeSet(f"{target!r} is not an entity this candidate can see, so it cannot be removed here.")
    kept = held.without(lambda op: isinstance(op, EditEntity) and op.target == target)
    return _Set(kept).put(RemoveEntity(target=target, base=BaseRevision(record_revision(current))))


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
    return _Set(kept).put(RemoveConnection(address=address, base=BaseRevision(record_revision(current))))


#: One recorder per edit. The six are the operations a change set is made of.
_RECORDERS: Mapping[str, Callable[[_Set, Intent, ModelReading], tuple[Operation, ...]]] = {
    "create_entity": _create_entity,
    "edit_entity": _edit_entity,
    "remove_entity": _remove_entity,
    "add_connection": _add_connection,
    "edit_connection": _edit_connection,
    "remove_connection": _remove_connection,
}
