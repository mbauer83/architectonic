"""Withdrawing a target state: taking out of the model what applying a candidate as one wrote.

A candidate applied as a target state (`target_state`) wrote its proposal beside the baseline. Withdrawing it
removes that again and leaves the baseline as it was, so the candidate is free to be applied, applied as a
target state again, rejected or deleted. The list is:

* every relation the target state wrote — the copies' relations, each the mirror of an original's or one the
  candidate adds; the traces from the copies to their originals; the relations of the elements it added that
  the candidate adds; the plateaus' aggregations and the gap's associations — and then
* the copies, the elements it added, the plateaus and the gap themselves.

**Nothing written since is removed with it.** A relation to one of those elements that the target state did
not write — drawn to a copy while it stood, say — is named, and the withdrawal is refused until it is
resolved; removing it silently would lose work nobody asked to lose. Which diagrams draw one of the elements is
the caller's to read; it is passed in as *drawn_by* and refuses in the same way.

**Pure.** The caller reads the model over everything named here and writes the result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from src.application.change_sets.base import BaseRevision, record_revision
from src.application.change_sets.candidate_architecture import CandidateArchitecture, TargetState
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.reading import RecordedReading
from src.domain.artifact_id import canonical_entity_key
from src.domain.ontology_representation.target_state_relations import TargetStateRelations
from src.domain.provisional_reference import provisional


@dataclass(frozen=True, slots=True)
class Withdrawal:
    """What withdrawing a target state removes, and what holds on to it: empty when nothing does."""

    changes: ChangeSet
    #: Relations to the target state's elements that it did not write, each as its address.
    foreign: tuple[ConnectionAddress, ...] = ()
    #: Each diagram that draws one of its elements, with the elements it draws.
    drawn: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def refusal(self) -> str | None:
        """The sentence that refuses the withdrawal while something written since holds on to it."""
        held = [
            *(f"the relation {a.source_entity} -{a.connection_type}-> {a.target_entity}" for a in self.foreign),
            *(f"the diagram {diagram} (draws {', '.join(ids)})" for diagram, ids in dict(self.drawn).items()),
        ]
        if not held:
            return None
        return (
            f"The target state cannot be withdrawn while what was written since refers to it: {'; '.join(held)}. "
            "Remove those references, or move the target state into the baseline instead."
        )


def withdrawal_of(
    candidate: CandidateArchitecture, state: TargetState, live: RecordedReading, *, revision: str,
    relations: TargetStateRelations, drawn_by: Mapping[str, Sequence[str]] | None = None,
) -> Withdrawal:
    """The operations that take *candidate*'s target *state* out of the *live* model, and what refuses them.

    *relations* are the ones the target state was written with; *drawn_by* maps a diagram's id to the
    target state's elements it draws.
    """
    written = {canonical_entity_key(ref) for ref in (*state.written, *state.added.values())}
    own = _Written.of(candidate, state, live, relations).relation
    cut, foreign = [], []
    for address, fields in sorted(live.connections.items(), key=lambda pair: str(pair[0])):
        if not set(address.endpoints) & written:
            continue
        if own(address):
            cut.append(RemoveConnection(address, BaseRevision(record_revision(fields))))
        else:
            foreign.append(address)
    gone = tuple(
        RemoveEntity(ref, BaseRevision(record_revision(fields)))
        for ref in sorted(written) if (fields := live.entity(ref)) is not None
    )
    drawn = {diagram: tuple(sorted(ids)) for diagram, ids in sorted((drawn_by or {}).items()) if ids}
    return Withdrawal(ChangeSet((*cut, *gone), revision), tuple(foreign), drawn)


@dataclass(frozen=True, slots=True)
class _Written:
    """What applying a candidate as a target state wrote, told from what was written since by what the apply
    generated it from: a copy's relation mirrors one its original holds or is one the candidate adds; an added
    element's relation is one the candidate adds; a trace runs from a copy to its own original; a plateau
    aggregates, and the gap associates the plateaus."""

    #: Each copy's original, and each added element's provisional reference, by the stable id written.
    originals: Mapping[str, str]
    aliases: Mapping[str, str]
    plateaus: frozenset[str]
    gap: str
    added_by_candidate: frozenset[ConnectionAddress]
    live: RecordedReading
    relations: TargetStateRelations

    @classmethod
    def of(
        cls, candidate: CandidateArchitecture, state: TargetState, live: RecordedReading,
        relations: TargetStateRelations,
    ) -> _Written:
        return cls(
            originals={canonical_entity_key(copy): original for original, copy in state.copies.items()},
            aliases={canonical_entity_key(added): provisional(alias) for alias, added in state.added.items()},
            plateaus=frozenset({canonical_entity_key(state.baseline), canonical_entity_key(state.target)}),
            gap=canonical_entity_key(state.gap),
            added_by_candidate=frozenset(
                op.address for op in candidate.changes.operations if isinstance(op, AddConnection)
            ),
            live=live,
            relations=relations,
        )

    def relation(self, address: ConnectionAddress) -> bool:
        source, kind, target = address.source_entity, address.connection_type, address.target_entity
        if source in self.plateaus:
            return kind == self.relations.holds
        if source == self.gap:
            return kind == self.relations.trace and target in self.plateaus
        if target in self.plateaus or target == self.gap:
            return False
        if kind == self.relations.trace and self.originals.get(source) == target:
            return True
        mapped = ConnectionAddress(self._back(source), kind, self._back(target))
        mirrored = mapped != address and self.live.connection(mapped) is not None
        return mapped in self.added_by_candidate or mirrored

    def _back(self, end: str) -> str:
        return self.originals.get(end, self.aliases.get(end, end))
