"""The operations a change set is made of: a closed union of six.

Create, edit and remove an entity; add, edit and remove a connection. This is the bulk write's
vocabulary plus removal, and it is closed for the reason the artifact kinds are: a seventh operation
is a decision about what a change to the model can be, not a key someone adds in passing.

**An edit addresses one thing with a name.** Which thing depends on the field, and the field
catalogue says which: one key of a mapping the write path patches key by key, the whole of a prose
field, or the whole of a value that is compared as a value. Never a position — `properties[3]` means
something else after an unrelated insert, and a change set exists to be read against a model that
moved.

**The vocabulary is derived, never restated.** Every field name here comes from
`edit_field_catalogue`, which the write functions, the REST bodies, the bulk decoder and a proposed
change already share. A fifth spelling would drift as the third one did.

**An entity is named in its stable form.** An operation is built from whatever spelling its author
held — the short id, or the id with its slug — and keeps the stable one (`canonical_entity_key`, the
id form's owner). Two operations naming one entity are then one claim however each was spelled, a
connection to an entity the set creates finds it, and a recorded set does not carry a slug a later
rename makes stale.

**Each operation refuses to exist malformed**, in a sentence that names the fix: these are built
where an author is present to correct them, and read back from a file where nobody is.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple, TypeAlias

from src.application.change_sets.base import Base, BaseRevision, BaseValue
from src.application.modeling.edit_field_catalogue import (
    CONTENT,
    KEYED,
    PROSE,
    ArtifactKind,
    creatable,
)
from src.domain.artifact_id import canonical_entity_key
from src.domain.provisional_reference import provisional


class MalformedChangeSet(ValueError):
    """A change set, or one of its operations, that cannot exist as stated. The message says why."""


def _keep_stable(operation: object, attribute: str) -> None:
    """Hold *attribute* in its stable spelling. A provisional reference is not an id and stays as written."""
    object.__setattr__(operation, attribute, canonical_entity_key(getattr(operation, attribute)))


@dataclass(frozen=True, slots=True, order=True)
class ConnectionAddress:
    """What identifies a connection: its endpoints and its type. It has no id of its own.

    The attribute names are the catalogue's `ADDRESSING["connection"]`. An endpoint is an entity id
    or a provisional reference to an entity a set creates.
    """

    source_entity: str
    connection_type: str
    target_entity: str

    def __post_init__(self) -> None:
        if not (self.source_entity and self.connection_type and self.target_entity):
            raise MalformedChangeSet(
                "a connection is addressed by its source, its type and its target, and all three "
                "are named"
            )
        _keep_stable(self, "source_entity")
        _keep_stable(self, "target_entity")

    @property
    def endpoints(self) -> tuple[str, str]:
        return (self.source_entity, self.target_entity)

    def __str__(self) -> str:
        return f"{self.source_entity} —{self.connection_type}→ {self.target_entity}"


class OperationKey(NamedTuple):
    """The one thing an operation changes — its claim. A set holds at most one operation per claim.

    `field` is empty where the operation is about the artifact as a whole — creating or removing it —
    and `key` is empty unless the field is a mapping patched key by key.
    """

    kind: ArtifactKind
    subject: str | ConnectionAddress
    field: str = ""
    key: str = ""

    def __str__(self) -> str:
        where = ".".join(part for part in (self.field, self.key) if part)
        return f"{where} of {self.subject}" if where else f"{self.subject}"


def _check_edit(kind: ArtifactKind, field: str, key: str | None, base: Base) -> None:
    """Refuse an edit whose address or base does not fit the field it names."""
    if field not in CONTENT[kind]:
        raise MalformedChangeSet(
            f"{field!r} is not a field of a {kind} that an edit may change. "
            f"Accepted: {', '.join(sorted(CONTENT[kind]))}."
        )
    if field in KEYED[kind]:
        if not key:
            raise MalformedChangeSet(
                f"an edit of {field!r} names the one key it changes. The field is patched key by "
                "key, so replacing it whole would remove every key the edit did not mention."
            )
    elif key is not None:
        raise MalformedChangeSet(
            f"{field!r} has no keys to address, so an edit of it carries none (it named {key!r})."
        )
    if field in PROSE[kind]:
        if not isinstance(base, BaseRevision):
            raise MalformedChangeSet(
                f"{field!r} is prose, and an edit of prose records the revision of the text it "
                "replaces rather than the text."
            )
    elif not isinstance(base, BaseValue):
        raise MalformedChangeSet(
            f"an edit of {field!r} records the value it replaces. A revision is recorded only for "
            "prose, where the value is too large to carry."
        )


def _check_stated(kind: ArtifactKind, fields: Mapping[str, Any], required: tuple[str, ...]) -> None:
    """Refuse a create that states a field its kind does not have, or omits one it cannot lack."""
    unknown = sorted(set(fields) - creatable(kind))
    if unknown:
        raise MalformedChangeSet(
            f"{unknown} {'is' if len(unknown) == 1 else 'are'} not something a new {kind} states. "
            f"Accepted: {', '.join(sorted(creatable(kind)))}."
        )
    missing = [name for name in required if not fields.get(name)]
    if missing:
        raise MalformedChangeSet(f"a new {kind} states its {' and its '.join(missing)}")


@dataclass(frozen=True, slots=True)
class CreateEntity:
    """A new entity, known to the rest of its set by the alias `ref`.

    `fields` is everything the create states, in the catalogue's names. `group` is the group's id,
    not its slug: a slug is a directory name and changes when the group is renamed, and a set that
    outlives a rename would file its entity under a name that no longer exists.
    """

    ref: str
    fields: Mapping[str, Any]
    #: An id chosen in advance instead of allocated. The rest of the set still uses the alias.
    artifact_id: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.ref:
            raise MalformedChangeSet(
                "a new entity carries an alias: it is how the rest of the set names it before it "
                "has an id"
            )
        _check_stated("entity", self.fields, ("artifact_type", "name", "group"))

    @property
    def reference(self) -> str:
        """How other operations in the set name this entity."""
        return provisional(self.ref)

    @property
    def claim(self) -> OperationKey:
        return OperationKey("entity", self.reference)


@dataclass(frozen=True, slots=True)
class EditEntity:
    """One named thing about one entity, changed to `value`. A `None` value removes a key."""

    target: str
    field: str
    value: Any
    base: Base
    key: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.target:
            raise MalformedChangeSet("an edit names the entity it changes")
        _keep_stable(self, "target")
        _check_edit("entity", self.field, self.key, self.base)

    @property
    def claim(self) -> OperationKey:
        return OperationKey("entity", self.target, self.field, self.key or "")


@dataclass(frozen=True, slots=True)
class RemoveEntity:
    """An entity taken out of the model. `base` is the revision of the record that was read."""

    target: str
    base: BaseRevision
    note: str = ""

    def __post_init__(self) -> None:
        if not self.target:
            raise MalformedChangeSet("a removal names the entity it removes")
        _keep_stable(self, "target")
        _check_removal_base(self.base)

    @property
    def claim(self) -> OperationKey:
        return OperationKey("entity", self.target)


@dataclass(frozen=True, slots=True)
class AddConnection:
    """A new connection between two entities, either of which the same set may create."""

    address: ConnectionAddress
    fields: Mapping[str, Any]
    note: str = ""

    def __post_init__(self) -> None:
        _check_stated("connection", self.fields, ())

    @property
    def claim(self) -> OperationKey:
        return OperationKey("connection", self.address)


@dataclass(frozen=True, slots=True)
class EditConnection:
    """One named thing about one connection, changed to `value`. A `None` value removes a key."""

    address: ConnectionAddress
    field: str
    value: Any
    base: Base
    key: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        _check_edit("connection", self.field, self.key, self.base)

    @property
    def claim(self) -> OperationKey:
        return OperationKey("connection", self.address, self.field, self.key or "")


@dataclass(frozen=True, slots=True)
class RemoveConnection:
    """A connection taken out of the model. `base` is the revision of the record that was read."""

    address: ConnectionAddress
    base: BaseRevision
    note: str = ""

    def __post_init__(self) -> None:
        _check_removal_base(self.base)

    @property
    def claim(self) -> OperationKey:
        return OperationKey("connection", self.address)


def _check_removal_base(base: object) -> None:
    if not isinstance(base, BaseRevision):
        raise MalformedChangeSet(
            "a removal records the revision of the record it removes, so that a record someone "
            "changed in the meantime is not removed unseen"
        )


#: Everything a change set can ask of the model.
Operation: TypeAlias = (
    CreateEntity | EditEntity | RemoveEntity | AddConnection | EditConnection | RemoveConnection
)

#: The operations that change one named thing about something that exists.
Edit: TypeAlias = EditEntity | EditConnection


def entities_used(operation: Operation) -> tuple[str, ...]:
    """The entities that must exist for *operation* to mean anything.

    A removal uses nothing: it is satisfied by absence. Removing a connection does not need its
    endpoints either — which is what lets one set remove an entity together with its connections.
    """
    match operation:
        case EditEntity(target=target):
            return (target,)
        case AddConnection(address=address) | EditConnection(address=address):
            return address.endpoints
        case _:
            return ()


def sort_key(operation: Operation) -> tuple[str, tuple[str, ...], str, str]:
    """A total order over operations by what they change, so a set has one canonical arrangement."""
    claim = operation.claim
    subject = claim.subject
    parts = (
        (subject,)
        if isinstance(subject, str)
        else (subject.source_entity, subject.connection_type, subject.target_entity)
    )
    return (claim.kind, parts, claim.field, claim.key)
