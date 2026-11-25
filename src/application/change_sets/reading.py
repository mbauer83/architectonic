"""What a change set needs to know about the model, and nothing more.

Every judgement about a set — where each operation stands, what the model would say with the set
applied — asks the model two questions: what does this entity say, and what does this connection
say. They are asked through this protocol so that the model can be a repository's index, a set
already composed onto one, or three records a test wrote down.

**Field values are in the edit vocabulary.** The names are `edit_field_catalogue`'s, which is what
`current_values_of` already answers in for an entity — so an adapter over the real model is a thin
one, and an operation's field is looked up under the name the operation uses.

**Absent is `None`, at both levels.** An artifact that does not exist reads as `None`. A field the
reading does not carry is simply not in the mapping, and callers treat that as *no evidence* — never
as "empty" — for the reason integration detection gives: a field nobody could read has not been
shown to differ.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeAlias

from src.application.change_sets.operations import ConnectionAddress
from src.domain.artifact_id import canonical_entity_key

#: One artifact's current fields, by the edit vocabulary's names.
FieldValues: TypeAlias = Mapping[str, Any]


class ModelReading(Protocol):
    """The model as a change set sees it: what an entity says, and what a connection says."""

    def entity(self, reference: str) -> FieldValues | None:
        """The entity's fields, or None where there is no such entity."""
        ...

    def connection(self, address: ConnectionAddress) -> FieldValues | None:
        """The connection's fields, or None where there is no such connection."""
        ...


@dataclass(frozen=True, slots=True)
class RecordedReading:
    """A reading held as plain records: the model a caller wrote down, or read off beforehand."""

    entities: Mapping[str, FieldValues] = field(default_factory=dict)
    connections: Mapping[ConnectionAddress, FieldValues] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Held by the stable id, as operations name what they touch: either spelling finds the record.
        stable = {canonical_entity_key(ref): fields for ref, fields in self.entities.items()}
        object.__setattr__(self, "entities", stable)

    def entity(self, reference: str) -> FieldValues | None:
        return self.entities.get(canonical_entity_key(reference))

    def connection(self, address: ConnectionAddress) -> FieldValues | None:
        return self.connections.get(address)
