"""The change set: operations on the model, with what each was written against. Not yet the model.

This is the one operation value under everything that holds changes for a while. A candidate
architecture holds one and adds a name, a rationale and a place in the work. A diagram edit session
holds one in memory until *Save*. A proposed change is one waiting on a reviewer. They differ in who
made them and what becomes of them; what they *say* — these operations, against these bases — is the
same, and is said here once so that two artifacts do not become two engines.

**It therefore carries nothing only one of them has.** No name, no rationale, no lifecycle state, no
parent, nothing it answers or satisfies: those belong to the candidate architecture
(`candidate_architecture`). A set is also not identified here — whoever holds several names them.
What it does carry is what any reader of the operations needs: the repository revision the bases
were read at, and the version of the operation vocabulary it is written in.

**A value, and nothing else.** No file, no repository, no request. Everything that reads or judges a
set is a pure function over this value and a reading of the model that the caller supplies.

**It lives in the application layer, though it is pure.** Its field vocabulary is derived from
`edit_field_catalogue`, which is kept at this layer because it describes what the write path accepts
rather than what the ontology declares. A domain module may import only the domain, so a change set
kept there would have had to restate the vocabulary — the one thing it must not do.

**Operations have no authored order.** They are kept in one canonical arrangement, so two sets
holding the same operations are equal however they were assembled, and the order an applier needs is
derived from what the operations refer to (`ordering`).

**A reference nothing in the set creates is not refused here.** A set read on top of another may
name what the lower one creates, and a set does not know whether it will be. That is settled where
the layers are in hand: `ordering.application_order`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.application.change_sets.coherence import created_by, first_refusal
from src.application.change_sets.operations import (
    CreateEntity,
    MalformedChangeSet,
    Operation,
    OperationKey,
    sort_key,
)

#: The version of the operation vocabulary this code reads and writes. A set records the one it was
#: written under so that an upgrade step can tell which sets it has to rewrite.
FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """Operations, and what they were written against. Refuses to exist malformed."""

    operations: tuple[Operation, ...]
    #: The repository revision the operations' bases were read at.
    repository_revision: str
    format_version: int = FORMAT_VERSION

    def __post_init__(self) -> None:
        refusal = _written_under_refusal(self) or first_refusal(self.operations)
        if refusal is not None:
            raise MalformedChangeSet(refusal)
        # One canonical arrangement: equality and the recorded form do not depend on assembly order.
        object.__setattr__(self, "operations", tuple(sorted(self.operations, key=sort_key)))

    @property
    def created(self) -> Mapping[str, CreateEntity]:
        """The entities this set creates, by the reference its other operations name them with."""
        return created_by(self.operations)

    @property
    def by_claim(self) -> Mapping[OperationKey, Operation]:
        """Each operation under the one thing it changes."""
        return {operation.claim: operation for operation in self.operations}


def _written_under_refusal(change_set: ChangeSet) -> str | None:
    if not change_set.repository_revision:
        return (
            "a change set says which repository revision it was written against. Without it "
            "nobody can tell whether the model has moved since."
        )
    if change_set.format_version != FORMAT_VERSION:
        return (
            f"this change set is written in format {change_set.format_version}, and this version "
            f"reads format {FORMAT_VERSION}. Upgrade the repository, or the product."
        )
    return None
