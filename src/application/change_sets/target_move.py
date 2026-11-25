"""Moving a target state into the baseline: one generated operation list, judged like any other.

What a candidate applied as a target state wrote beside the baseline (`target_state`) is taken back into
it. The list is:

* the candidate's own operations, applied to the originals, with the elements it added named by the
  ids they were given — the kept change set, checked against the model as it is now, so an original
  someone changed meanwhile reads as drifted and the move is re-based or refused like any apply;
* each element it added set from draft to what its create states, or active;
* each relation a "(target)" copy holds that the originals do not, moved to the originals — one drawn
  to a copy while the target state stood is not lost;
* every relation of the copies, the plateaus and the gap removed, and then those elements themselves:
  afterwards there is one state, so no plateau or gap applies.

**Pure.** The caller reads the model over everything named here and writes the result.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from src.application.change_sets.base import BaseRevision, BaseValue, record_revision
from src.application.change_sets.candidate_architecture import CandidateArchitecture, TargetState
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.composition import compose
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
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.target_state import ACTIVE, DRAFT, TRACE, stated
from src.domain.artifact_id import canonical_entity_key
from src.domain.provisional_reference import alias_of


def move_into_baseline(
    candidate: CandidateArchitecture, state: TargetState, live: RecordedReading, *, revision: str,
) -> ChangeSet:
    """The operations that move *candidate*'s target *state* into the baseline, over the *live* model."""
    kept = tuple(
        settled for operation in candidate.changes.operations
        if (settled := _named_by_id(operation, state.added)) is not None
    )
    activated = tuple(
        EditEntity(state.added[create.ref], "status", str(create.fields.get("status") or ACTIVE), BaseValue(DRAFT))
        for create in candidate.changes.created.values() if create.ref in state.added
    )
    composed = compose(ChangeSet(kept, revision), live)
    claimed = {operation.claim for operation in kept}
    removed = {op.target for op in kept if isinstance(op, RemoveEntity)}
    originals = {canonical_entity_key(copy): original for original, copy in state.copies.items()}
    containers = {canonical_entity_key(ref) for ref in (state.baseline, state.target, state.gap)}
    taken = set(originals) | containers
    cut, moved = [], []
    for address, fields in sorted(live.connections.items(), key=lambda pair: str(pair[0])):
        if not set(address.endpoints) & taken:
            continue
        cut.append(RemoveConnection(address, BaseRevision(record_revision(fields))))
        back = ConnectionAddress(
            originals.get(address.source_entity, address.source_entity), address.connection_type,
            originals.get(address.target_entity, address.target_entity),
        )
        if (
            set(address.endpoints) & containers or set(back.endpoints) & removed or _traces(address, originals)
            or back.source_entity == back.target_entity or AddConnection(back, {}).claim in claimed
            or composed.connection(back) is not None
        ):
            continue
        moved.append(AddConnection(back, stated(fields, "connection")))
    gone = tuple(
        RemoveEntity(ref, BaseRevision(record_revision(fields)))
        for ref in state.written if (fields := live.entity(ref)) is not None
    )
    return ChangeSet((*kept, *activated, *_once(moved), *cut, *gone), revision)


def _named_by_id(operation: Operation, added: Mapping[str, str]) -> Operation | None:
    """*operation* with each element the target state added named by its id; None for the create itself."""

    def by_id(reference: str) -> str:
        alias = alias_of(reference)
        return added.get(alias, reference) if alias is not None else reference

    match operation:
        case CreateEntity():
            return None
        case EditEntity(target=target) | RemoveEntity(target=target):
            return replace(operation, target=by_id(target))
        case AddConnection(address=address) | EditConnection(address=address) | RemoveConnection(address=address):
            return replace(operation, address=ConnectionAddress(
                by_id(address.source_entity), address.connection_type, by_id(address.target_entity),
            ))


def _traces(address: ConnectionAddress, originals: Mapping[str, str]) -> bool:
    """Whether *address* is the association that traces a copy to its original."""
    return address.connection_type == TRACE and originals.get(address.source_entity) == address.target_entity


def _once(additions: list[AddConnection]) -> tuple[AddConnection, ...]:
    """One addition per relation: two copies' relations can move back onto the same originals."""
    return tuple({addition.address: addition for addition in additions}.values())
