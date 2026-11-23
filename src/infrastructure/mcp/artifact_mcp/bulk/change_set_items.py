"""A change set's operations as bulk items, and bulk items as operations — pure, over plain mappings.

The two vocabularies say the same things at different grain. A bulk `edit_entity` item changes
several fields of one entity and patches several keys of `properties`; a change set holds one
operation per field and per key, each with the base it was written against. So one item becomes
several operations and several operations fold back into one item, and what an item cannot carry —
a base, a note — is supplied by the caller or dropped, and said so here.

It lives beside the decoder because the wire envelope does: `op`, `_ref` and `operation` are the
bulk request's spellings, and `KNOWN_ITEM_FIELDS` is the decoder's own account of what an item may
carry. The reader (`change_set_item_reading`) asks it; what this module writes is held to it by the
round trip, which passes every written item back through the decoder's own check.

**Removal is split across two tools today.** A connection can be removed by the bulk write
(`edit_connection` with `operation: remove`); an entity only by the bulk delete. So a set translates
to two lists, and `delete_connection` is accepted on the way in as the same removal.

**What does not translate is refused, in a sentence**, rather than approximated:
`create_document` and the document and diagram deletes have no operation in a set; a create without
`_ref` has nothing for the set to call it; a keyed field sent as `null` clears keys the item does
not name, which a set — one operation per named key — cannot say; and the bulk write resolves a
provisional reference only in the endpoints of an `add_connection`, so an edit or a removal aimed at
one has to be given the id it resolved to.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditConnection,
    EditEntity,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.ordering import application_order
from src.application.modeling.edit_field_catalogue import ADDRESSING, KEYED, ArtifactKind
from src.domain.provisional_reference import alias_of

#: One bulk item, as the tools take it.
Item: TypeAlias = dict[str, Any]

#: A group's slug for its id, or its id for its slug. A set names a group by id; an item by slug.
GroupName: TypeAlias = Callable[[str], str]

#: How an entity is addressed — the catalogue's one name for it.
(ARTIFACT_ID,) = ADDRESSING["entity"]


class Untranslatable(ValueError):
    """Something one vocabulary says that the other cannot. The message says what, and what to do."""


@dataclass(frozen=True, slots=True)
class BulkItems:
    """A set's operations as the two bulk tools take them."""

    #: For `artifact_bulk_write`, in an order that applies.
    write: tuple[Item, ...]
    #: For `artifact_bulk_delete`: the entity removals, which the bulk write cannot perform.
    delete: tuple[Item, ...]


def to_bulk_items(
    change_set: ChangeSet,
    *,
    slug_of_group: GroupName,
    resolved: Mapping[str, str] | None = None,
    beneath: ChangeSet | None = None,
) -> BulkItems:
    """The set's operations as bulk items. Bases and notes are not carried: an item has no place for them.

    `resolved` gives the id each provisional reference became, for a set applied after the one beneath it.
    """
    known = resolved or {}
    created = frozenset(change_set.created)
    operations = application_order(change_set, beneath=(beneath,) if beneath else ())

    def settled(reference: str, *, may_stay_provisional: bool = False) -> str:
        alias = alias_of(reference)
        if alias is None:
            return reference
        if alias in known:
            return known[alias]
        if may_stay_provisional and reference in created:
            return reference
        raise Untranslatable(
            f"{reference} has no id yet. The bulk write resolves a provisional reference only in "
            "the endpoints of a connection it adds in the same batch; apply the set that creates "
            "it first and pass the id it was given."
        )

    def address(of: ConnectionAddress, *, adding: bool = False) -> Item:
        return {
            "source_entity": settled(of.source_entity, may_stay_provisional=adding),
            "connection_type": of.connection_type,
            "target_entity": settled(of.target_entity, may_stay_provisional=adding),
        }

    creates = [
        {"op": "create_entity", "_ref": op.ref, **_chosen(op), **with_group_named(op.fields, slug_of_group)}
        for op in operations
        if isinstance(op, CreateEntity)
    ]
    adds = [
        {"op": "add_connection", **address(op.address, adding=True), **op.fields}
        for op in operations
        if isinstance(op, AddConnection)
    ]
    entity_edits = _folded(
        ((settled(op.target), op) for op in operations if isinstance(op, EditEntity)),
        lambda target: {"op": "edit_entity", ARTIFACT_ID: target},
        "entity",
        slug_of_group,
    )
    connection_edits = _folded(
        ((op.address, op) for op in operations if isinstance(op, EditConnection)),
        lambda of: {"op": "edit_connection", **address(of)},
        "connection",
        slug_of_group,
    )
    cuts = [
        {"op": "edit_connection", **address(op.address), "operation": "remove"}
        for op in operations
        if isinstance(op, RemoveConnection)
    ]
    deletes = [
        {"op": "delete_entity", ARTIFACT_ID: settled(op.target)}
        for op in operations
        if isinstance(op, RemoveEntity)
    ]
    return BulkItems(
        write=(*creates, *adds, *entity_edits, *connection_edits, *cuts), delete=tuple(deletes)
    )


def _chosen(create: CreateEntity) -> Item:
    return {ARTIFACT_ID: create.artifact_id} if create.artifact_id else {}


def with_group_named(fields: Mapping[str, Any], name_of: GroupName) -> Item:
    """*fields*, with a group named the way the other vocabulary names it."""
    return {
        name: name_of(value) if name == "group" and isinstance(value, str) else value
        for name, value in fields.items()
    }


def _folded(
    edits: Iterable[tuple[Any, EditEntity | EditConnection]],
    head: Callable[[Any], Item],
    kind: ArtifactKind,
    slug_of_group: GroupName,
) -> list[Item]:
    """One item per subject: its whole-field edits as fields, its keyed edits gathered per field."""
    items: dict[Any, Item] = {}
    for subject, edit in edits:
        item = items.setdefault(subject, head(subject))
        if edit.field in KEYED[kind]:
            item.setdefault(edit.field, {})[edit.key] = edit.value
        else:
            item.update(with_group_named({edit.field: edit.value}, slug_of_group))
    return list(items.values())
