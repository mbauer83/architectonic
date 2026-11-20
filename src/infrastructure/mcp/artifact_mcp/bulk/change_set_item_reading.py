"""Bulk items read as a change set's operations: one per field and per key an item changes.

The other half of `change_set_items`, which says what the two vocabularies share and where they
part. Kept apart from it because reading is where every refusal lives: an item is a caller's request,
and what a set cannot hold is said here before a set is built from it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeAlias

from src.application.change_sets.base import Base, BaseRevision
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditConnection,
    EditEntity,
    Operation,
    OperationKey,
    RemoveConnection,
    RemoveEntity,
)
from src.application.modeling.edit_field_catalogue import CONTENT, KEYED, ArtifactKind, creatable
from src.domain.repository.groups import UNCATEGORIZED

from .change_set_items import ARTIFACT_ID, GroupName, Untranslatable, with_group_named
from .common import KNOWN_DELETE_OPS, KNOWN_OPS, unknown_item_fields

#: The base an operation should record, for the one thing it changes. An item carries none.
BaseOf: TypeAlias = Callable[[OperationKey], Base]


def from_bulk_items(
    write: Sequence[Mapping[str, Any]],
    delete: Sequence[Mapping[str, Any]] = (),
    *,
    id_of_group: GroupName,
    base_of: BaseOf,
) -> tuple[Operation, ...]:
    """The operations these items amount to: one per field and per key they change.

    `base_of` supplies what each operation was written against — the caller read the model, the item
    did not record it. What the items say twice, or contradict, is refused when the operations are
    put in a set, not here.
    """
    return tuple(
        operation for item in (*write, *delete) for operation in _read(item, id_of_group, base_of)
    )


def _read(item: Mapping[str, Any], id_of_group: GroupName, base_of: BaseOf) -> list[Operation]:
    op = str(item.get("op", ""))
    if op not in KNOWN_OPS | KNOWN_DELETE_OPS:
        raise Untranslatable(f"{op!r} is not a bulk operation")
    stray = unknown_item_fields(dict(item))
    if stray:
        raise Untranslatable(f"a {op} item does not take {list(stray)}")
    match op:
        case "create_entity":
            return [_read_create(item, id_of_group)]
        case "add_connection":
            stated = {name: item[name] for name in sorted(creatable("connection")) if name in item}
            return [AddConnection(_read_address(item), stated)]
        case "edit_entity":
            target = _required(item, ARTIFACT_ID)
            return _read_edits(item, "entity", target, id_of_group, base_of)
        case "edit_connection":
            return _read_connection_edit(item, id_of_group, base_of)
        case "delete_entity":
            target = _required(item, ARTIFACT_ID)
            return [RemoveEntity(target, _removal_base(base_of, OperationKey("entity", target)))]
        case "delete_connection":
            return [_read_removal(item, base_of)]
        case _:
            raise Untranslatable(
                f"a change set has no operation for {op}: it changes entities and connections. "
                "Documents and diagrams are written by their own tools."
            )


def _read_create(item: Mapping[str, Any], id_of_group: GroupName) -> Operation:
    if not item.get("_ref"):
        raise Untranslatable(
            "a create_entity item needs a _ref to be put in a change set: the alias is how the "
            "rest of the set names the entity, and how two creates are told apart"
        )
    stated = {name: item[name] for name in sorted(creatable("entity")) if name in item}
    stated["group"] = id_of_group(str(item.get("group") or UNCATEGORIZED))
    return CreateEntity(ref=str(item["_ref"]), fields=stated, artifact_id=item.get(ARTIFACT_ID))


def _read_connection_edit(
    item: Mapping[str, Any], id_of_group: GroupName, base_of: BaseOf
) -> list[Operation]:
    mode = item.get("operation", "update")
    if mode == "update":
        return _read_edits(item, "connection", _read_address(item), id_of_group, base_of)
    if mode != "remove":
        raise Untranslatable(f"an edit_connection's operation is update or remove, not {mode!r}")
    carried = sorted(CONTENT["connection"] & set(item))
    if carried:
        raise Untranslatable(
            f"an edit_connection that removes the connection also sets {carried}. It cannot do "
            "both: drop the fields, or the removal."
        )
    return [_read_removal(item, base_of)]


def _read_removal(item: Mapping[str, Any], base_of: BaseOf) -> Operation:
    address = _read_address(item)
    return RemoveConnection(address, _removal_base(base_of, OperationKey("connection", address)))


def _read_edits(
    item: Mapping[str, Any],
    kind: ArtifactKind,
    subject: str | ConnectionAddress,
    id_of_group: GroupName,
    base_of: BaseOf,
) -> list[Operation]:
    """One operation per field the item changes, and per key of a field it patches."""
    operations: list[Operation] = []
    for field in sorted(CONTENT[kind] & set(item)):
        value = item[field]
        if field not in KEYED[kind]:
            said = with_group_named({field: value}, id_of_group)[field]
            operations.append(_edit(subject, field, said, base_of(OperationKey(kind, subject, field))))
            continue
        if not isinstance(value, Mapping):
            raise Untranslatable(
                f"{field!r} sent as {value!r} clears or replaces keys the item does not name, and "
                "a change set holds one operation per named key. Send each key, mapped to null to "
                "remove it."
            )
        operations.extend(
            _edit(subject, field, entry, base_of(OperationKey(kind, subject, field, str(key))), str(key))
            for key, entry in value.items()
        )
    if not operations:
        raise Untranslatable(f"an {item['op']} item that changes nothing is not an operation")
    return operations


def _read_address(item: Mapping[str, Any]) -> ConnectionAddress:
    return ConnectionAddress(
        source_entity=_required(item, "source_entity"),
        connection_type=_required(item, "connection_type"),
        target_entity=_required(item, "target_entity"),
    )


def _required(item: Mapping[str, Any], name: str) -> str:
    if not item.get(name):
        raise Untranslatable(f"a {item.get('op')} item names its {name}")
    return str(item[name])


def _removal_base(base_of: BaseOf, key: OperationKey) -> BaseRevision:
    base = base_of(key)
    if not isinstance(base, BaseRevision):
        raise Untranslatable(
            f"removing {key} records the revision of the record as it was read, and a value was "
            "supplied instead"
        )
    return base


def _edit(
    subject: str | ConnectionAddress, field: str, value: Any, base: Base, key: str | None = None
) -> Operation:
    """An edit of whichever kind of thing *subject* addresses."""
    if isinstance(subject, ConnectionAddress):
        return EditConnection(subject, field, value, base, key=key)
    return EditEntity(subject, field, value, base, key=key)
