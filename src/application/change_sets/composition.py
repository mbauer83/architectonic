"""What the model would say with a change set applied — computed, without applying anything.

A hypothetical read ("this entity, as if the adaptation were in") and an applier checking its own
result both need the same thing: the current field values of what the set touches, with the set's
operations laid over them. That is a reading like any other, so the result answers the same two
questions the model does and can be read by everything that reads the model — including another
composition, which is all that stacking is.

**An entity the set creates is read under its alias.** It has no id until something applies the
set, and inventing one here would be a second allocator.

**A removed entity takes its connections with it.** A connection whose endpoint the composition
removed reads as absent, whether or not the set removed it by name. The reading cannot enumerate an
entity's connections, and does not need to: it is asked about one connection at a time.

**What had nothing to apply to is reported, not dropped.** An edit of an entity that is gone
changes nothing in the composed state. Where each operation stands is `standing`'s to judge; here
they are only named, so a caller showing a hypothetical state can say what it does not include.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

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
)
from src.application.change_sets.ordering import application_order
from src.application.change_sets.reading import FieldValues, ModelReading
from src.application.modeling.edit_field_catalogue import KEYED, ArtifactKind
from src.domain.artifact_id import canonical_entity_key


@dataclass(frozen=True, slots=True)
class ComposedReading:
    """A reading with change sets laid over it. Itself a `ModelReading`."""

    beneath: ModelReading
    #: What the sets say about each entity they touch. `None` is a removal.
    entities: Mapping[str, FieldValues | None]
    #: What the sets say about each connection they touch. `None` is a removal.
    connections: Mapping[ConnectionAddress, FieldValues | None]
    #: The operations that found nothing to apply to, in the order they would have been applied.
    unapplied: tuple[Operation, ...] = ()

    def entity(self, reference: str) -> FieldValues | None:
        key = canonical_entity_key(reference)
        if key in self.entities:
            return self.entities[key]
        return self.beneath.entity(key)

    def connection(self, address: ConnectionAddress) -> FieldValues | None:
        if any(self.entities.get(end, ...) is None for end in address.endpoints):
            return None
        if address in self.connections:
            return self.connections[address]
        return self.beneath.connection(address)


def compose(
    change_set: ChangeSet, reading: ModelReading, *, beneath: Sequence[ChangeSet] = ()
) -> ComposedReading:
    """The model *reading* describes, with the set applied — on top of the sets beneath, lowest first.

    Each layer is applied as its own set, and may name what any layer under it creates. How deep a
    stack may be is not decided here. Refuses what `application_order` refuses: a reference nothing
    creates.
    """
    composed = ComposedReading(beneath=reading, entities={}, connections={})
    layers = (*beneath, change_set)
    for depth, layer in enumerate(layers):
        composed = _laid_over(composed, application_order(layer, beneath=layers[:depth]))
    return composed


def patched(kind: ArtifactKind, values: FieldValues, edit: EditEntity | EditConnection) -> FieldValues:
    """*values* with one edit applied: one key of a keyed field, or the field whole.

    The write path's own rule for a keyed field — a sent key is set, a key mapped to `None` is
    removed, the rest are kept — restated here only as far as one key.
    """
    if edit.field not in KEYED[kind]:
        return {**values, edit.field: edit.value}
    held = values.get(edit.field)
    entries = dict(held) if isinstance(held, Mapping) else {}
    if edit.value is None:
        entries.pop(str(edit.key), None)
    else:
        entries[str(edit.key)] = edit.value
    return {**values, edit.field: entries}


def _laid_over(composed: ComposedReading, operations: tuple[Operation, ...]) -> ComposedReading:
    entities: dict[str, FieldValues | None] = dict(composed.entities)
    connections: dict[ConnectionAddress, FieldValues | None] = dict(composed.connections)
    unapplied: list[Operation] = list(composed.unapplied)

    def now() -> ComposedReading:
        return ComposedReading(composed.beneath, entities, connections)

    for operation in operations:
        match operation:
            case CreateEntity(fields=fields):
                entities[operation.reference] = dict(fields)
            case EditEntity(target=target):
                current = now().entity(target)
                if current is None:
                    unapplied.append(operation)
                else:
                    entities[target] = patched("entity", current, operation)
            case RemoveEntity(target=target):
                entities[target] = None
            case AddConnection(address=address, fields=fields):
                if any(now().entity(end) is None for end in address.endpoints):
                    unapplied.append(operation)
                else:
                    connections[address] = dict(fields)
            case EditConnection(address=address):
                current = now().connection(address)
                if current is None:
                    unapplied.append(operation)
                else:
                    connections[address] = patched("connection", current, operation)
            case RemoveConnection(address=address):
                connections[address] = None
    return ComposedReading(composed.beneath, entities, connections, tuple(unapplied))

