"""A change set as plain data, and back — the form a store, a request or a browser session carries.

Not a file format. Where a set is kept and in what syntax is a separate decision; this is the
mapping any such form serialises, so that the reader and writer that eventually exist are thin, and
so that there is one place where a recorded set is refused.

**Strict on the way in.** A key this form does not define is refused rather than ignored: a
misspelt `base` would otherwise read as an operation with no base, and an ignored key is how an
`edit_connection` once ran as an update when a removal was asked for. Everything the value itself
refuses is refused here too, because construction is how the mapping is read.

**The set and nothing above it.** A candidate architecture's name, state and links are recorded by
`candidate_recorded_form`, around this mapping, so a holder with no header — a proposed change, an
edit session — records exactly this.

**The spellings.** Operation names and field names are the write path's (`edit_entity`,
`source_entity`): an operation is recognisably the bulk item it corresponds to. Header keys are
hyphenated, as the model's frontmatter is.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from typing import Any

from src.application.change_sets.base import Base, BaseRevision, BaseValue
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditConnection,
    EditEntity,
    MalformedChangeSet,
    Operation,
    RemoveConnection,
    RemoveEntity,
)
from src.application.modeling.edit_field_catalogue import ADDRESSING

_OP = "op"
_NOTE = "note"
_REF = "ref"
#: How an entity is addressed — the catalogue's one name for it, taken rather than respelt.
(_ARTIFACT_ID,) = ADDRESSING["entity"]
_FIELDS = "fields"
_FIELD = "field"
_KEY = "key"
_VALUE = "value"
_BASE = "base"
_REVISION = "revision"
#: How a connection is addressed, in the order the address states it.
_ADDRESS = tuple(part.name for part in dataclasses.fields(ConnectionAddress))

#: How an operation is named in the form: as recorded, or as a caller is answered it.
Shown = Callable[[Operation], Operation]


def as_recorded(operation: Operation) -> Operation:
    return operation


_REPOSITORY_REVISION = "repository-revision"
_FORMAT_VERSION = "format-version"
_OPERATIONS = "operations"


def to_mapping(change_set: ChangeSet, shown: Shown = as_recorded) -> dict[str, Any]:
    """The recorded form of a set: what it was written under, and its operations, each as *shown* names it —
    as recorded, unless the form answers a caller who names entities otherwise (`created_names`)."""
    return {
        _REPOSITORY_REVISION: change_set.repository_revision,
        _FORMAT_VERSION: change_set.format_version,
        _OPERATIONS: [operation_to_mapping(shown(operation)) for operation in change_set.operations],
    }


def from_mapping(recorded: object) -> ChangeSet:
    """Read a recorded set, refusing anything the value does not admit."""
    if not isinstance(recorded, Mapping):
        raise MalformedChangeSet(
            f"a recorded change set is a mapping, not {type(recorded).__name__}"
        )
    refuse_strangers(
        "a recorded change set", recorded, (_REPOSITORY_REVISION, _FORMAT_VERSION, _OPERATIONS), ()
    )
    operations = recorded[_OPERATIONS]
    if not isinstance(operations, list | tuple):
        raise MalformedChangeSet(
            f"a recorded change set's {_OPERATIONS!r} is a list, not {type(operations).__name__}"
        )
    return ChangeSet(
        operations=tuple(operation_from_mapping(operation) for operation in operations),
        repository_revision=str(recorded[_REPOSITORY_REVISION]),
        format_version=recorded[_FORMAT_VERSION],
    )


def operation_to_mapping(operation: Operation) -> dict[str, Any]:
    """One operation's recorded form. A note is recorded only where there is one."""
    recorded = _written(operation)
    return {**recorded, _NOTE: operation.note} if operation.note else recorded


def _written(operation: Operation) -> dict[str, Any]:
    match operation:
        case CreateEntity(ref=ref, fields=fields, artifact_id=artifact_id):
            chosen = {_ARTIFACT_ID: artifact_id} if artifact_id else {}
            return {_OP: "create_entity", _REF: ref, **chosen, _FIELDS: dict(fields)}
        case EditEntity(target=target):
            return {_OP: "edit_entity", _ARTIFACT_ID: target, **_edit(operation)}
        case RemoveEntity(target=target, base=base):
            return {_OP: "remove_entity", _ARTIFACT_ID: target, _BASE: _base(base)}
        case AddConnection(address=address, fields=fields):
            return {_OP: "add_connection", **_address(address), _FIELDS: dict(fields)}
        case EditConnection(address=address):
            return {_OP: "edit_connection", **_address(address), **_edit(operation)}
        case RemoveConnection(address=address, base=base):
            return {_OP: "remove_connection", **_address(address), _BASE: _base(base)}


def _edit(edit: EditEntity | EditConnection) -> dict[str, Any]:
    keyed = {_KEY: edit.key} if edit.key is not None else {}
    return {_FIELD: edit.field, **keyed, _VALUE: edit.value, _BASE: _base(edit.base)}


def _address(address: ConnectionAddress) -> dict[str, str]:
    return {name: getattr(address, name) for name in _ADDRESS}


def _base(base: Base) -> dict[str, Any]:
    match base:
        case BaseValue(value):
            return {_VALUE: value}
        case BaseRevision(revision):
            return {_REVISION: revision}


def operation_from_mapping(recorded: object) -> Operation:
    """Read one recorded operation, refusing an unknown op, a missing key and an unexpected one."""
    if not isinstance(recorded, Mapping):
        raise MalformedChangeSet(
            f"a recorded operation is a mapping, not {type(recorded).__name__}"
        )
    reader = _READERS.get(str(recorded.get(_OP, "")))
    if reader is None:
        raise MalformedChangeSet(
            f"{recorded.get(_OP)!r} is not an operation a change set has. "
            f"The operations are {', '.join(_READERS)}."
        )
    return reader(recorded)


def _read_create_entity(recorded: Mapping[str, Any]) -> Operation:
    refuse_strangers("create_entity", recorded, (_OP, _REF, _FIELDS), (_ARTIFACT_ID, _NOTE))
    return CreateEntity(
        ref=str(recorded[_REF]),
        fields=_mapping(recorded[_FIELDS], "create_entity"),
        artifact_id=recorded.get(_ARTIFACT_ID),
        note=str(recorded.get(_NOTE, "")),
    )


def _read_edit_entity(recorded: Mapping[str, Any]) -> Operation:
    refuse_strangers(
        "edit_entity", recorded, (_OP, _ARTIFACT_ID, _FIELD, _VALUE, _BASE), (_KEY, _NOTE)
    )
    return EditEntity(
        target=str(recorded[_ARTIFACT_ID]),
        field=str(recorded[_FIELD]),
        value=recorded[_VALUE],
        base=_read_base(recorded[_BASE]),
        key=recorded.get(_KEY),
        note=str(recorded.get(_NOTE, "")),
    )


def _read_remove_entity(recorded: Mapping[str, Any]) -> Operation:
    refuse_strangers("remove_entity", recorded, (_OP, _ARTIFACT_ID, _BASE), (_NOTE,))
    return RemoveEntity(
        target=str(recorded[_ARTIFACT_ID]),
        base=_read_removal_base(recorded[_BASE]),
        note=str(recorded.get(_NOTE, "")),
    )


def _read_add_connection(recorded: Mapping[str, Any]) -> Operation:
    refuse_strangers("add_connection", recorded, (_OP, *_ADDRESS, _FIELDS), (_NOTE,))
    return AddConnection(
        address=_read_address(recorded),
        fields=_mapping(recorded[_FIELDS], "add_connection"),
        note=str(recorded.get(_NOTE, "")),
    )


def _read_edit_connection(recorded: Mapping[str, Any]) -> Operation:
    refuse_strangers(
        "edit_connection", recorded, (_OP, *_ADDRESS, _FIELD, _VALUE, _BASE), (_KEY, _NOTE)
    )
    return EditConnection(
        address=_read_address(recorded),
        field=str(recorded[_FIELD]),
        value=recorded[_VALUE],
        base=_read_base(recorded[_BASE]),
        key=recorded.get(_KEY),
        note=str(recorded.get(_NOTE, "")),
    )


def _read_remove_connection(recorded: Mapping[str, Any]) -> Operation:
    refuse_strangers("remove_connection", recorded, (_OP, *_ADDRESS, _BASE), (_NOTE,))
    return RemoveConnection(
        address=_read_address(recorded),
        base=_read_removal_base(recorded[_BASE]),
        note=str(recorded.get(_NOTE, "")),
    )


#: One reader per operation. The union is closed, and so is this table.
_READERS: Mapping[str, Callable[[Mapping[str, Any]], Operation]] = {
    "create_entity": _read_create_entity,
    "edit_entity": _read_edit_entity,
    "remove_entity": _read_remove_entity,
    "add_connection": _read_add_connection,
    "edit_connection": _read_edit_connection,
    "remove_connection": _read_remove_connection,
}


def _read_address(recorded: Mapping[str, Any]) -> ConnectionAddress:
    return ConnectionAddress(**{name: str(recorded[name]) for name in _ADDRESS})


def _read_base(recorded: object) -> Base:
    """A recorded base: exactly one of the value that was there, or the revision of it."""
    if isinstance(recorded, Mapping) and set(recorded) == {_VALUE}:
        return BaseValue(recorded[_VALUE])
    if isinstance(recorded, Mapping) and set(recorded) == {_REVISION}:
        return BaseRevision(str(recorded[_REVISION]))
    raise MalformedChangeSet(
        f"a recorded base is either {{{_VALUE!r}: …}} or {{{_REVISION!r}: …}}, and this one is "
        f"{recorded!r}"
    )


def _read_removal_base(recorded: object) -> BaseRevision:
    base = _read_base(recorded)
    if not isinstance(base, BaseRevision):
        raise MalformedChangeSet(
            "a removal records the revision of the record it removes, and this one recorded a value"
        )
    return base


def _mapping(value: object, op: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MalformedChangeSet(
            f"a recorded {op}'s {_FIELDS!r} is a mapping, not {type(value).__name__}"
        )
    return dict(value)


def refuse_strangers(
    what: str, recorded: Mapping[str, Any], required: tuple[str, ...], optional: tuple[str, ...]
) -> None:
    """Refuse a mapping that lacks a key it must have, or carries one the form does not define."""
    missing = [key for key in required if key not in recorded]
    if missing:
        raise MalformedChangeSet(f"{what} is missing {missing}")
    unknown = sorted(str(key) for key in recorded if key not in (*required, *optional))
    if unknown:
        raise MalformedChangeSet(
            f"{what} carries {unknown}, which this form does not define. "
            f"It reads {', '.join((*required, *optional))}."
        )
