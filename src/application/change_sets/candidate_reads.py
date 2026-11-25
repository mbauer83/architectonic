"""Compose candidate reads over current scoped records: the composed view, a diff against a base, standing."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any, Protocol

from pydantic_core import to_jsonable_python

from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.candidate_view import CandidateView, difference, view_of
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.composition import compose
from src.application.change_sets.operations import ConnectionAddress, CreateEntity
from src.application.change_sets.reading import ModelReading, RecordedReading
from src.application.change_sets.recorded_form import operation_to_mapping
from src.application.change_sets.recording import rebased
from src.application.change_sets.stacking import descendants, sets_beneath, stack_of
from src.application.change_sets.standing import OperationStanding, standing_of
from src.application.modeling.edit_field_values import current_entity_values
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.artifact_id import canonical_entity_key


class CandidateLookup(Protocol):
    """Where candidates are found: by id, required by id, or all of them."""

    def find(self, ref: str) -> CandidateArchitecture | None: ...
    def require(self, ref: str) -> CandidateArchitecture: ...
    def list(self) -> Sequence[CandidateArchitecture]: ...


def live_reading(
    stack: tuple[CandidateArchitecture, ...], registry: ArtifactRegistry, also: Iterable[str] = (),
) -> RecordedReading:
    """The model's records over what the stack reads, and *also* what an edit about to be recorded names."""
    named = {ref for layer in stack for ref in layer.scope} | set(also)
    for layer in stack:
        for operation in layer.changes.operations:
            subject = operation.claim.subject
            named.update(subject.endpoints if isinstance(subject, ConnectionAddress) else (subject,))
            if isinstance(operation, CreateEntity) and operation.artifact_id:
                named.add(operation.artifact_id)
    # Every record is held by its stable id, as operations name what they touch (`operations`).
    refs = {canonical_entity_key(ref) for ref in named}
    entities, relations, stored = {}, {}, []
    for ref in sorted(refs):
        if (entity := registry.get_entity(ref)) is not None:
            entities[ref] = dict(current_entity_values(entity), artifact_type=entity.artifact_type)
            stored.append(entity.artifact_id)
    for artifact_id in stored:
        for conn in registry.find_connections_for(artifact_id):
            address = ConnectionAddress(conn.source, conn.conn_type, conn.target)
            relations[address] = {
                "description": conn.content_text, "metadata": dict(conn.attributes),
                "specializations": conn.specializations,
                "src_multiplicity": conn.src_multiplicity, "tgt_multiplicity": conn.tgt_multiplicity,
            }
    return RecordedReading(entities, relations)


def read_view(
    candidate: CandidateArchitecture, store: CandidateLookup, registry: ArtifactRegistry,
) -> CandidateView:
    stack = stack_of(candidate, store.find)
    return view_of(stack, live_reading(stack, registry))


def comparison(
    candidate: CandidateArchitecture, store: CandidateLookup, registry: ArtifactRegistry,
    *, base: str, naive: str | None,
) -> dict[str, Any]:
    stack = stack_of(candidate, store.find)
    live = live_reading(stack, registry)
    after = view_of(stack, live)
    if base == "model":
        before = CandidateView(
            dict(live.entities),
            {a: f for a, f in live.connections.items() if all(end in live.entities for end in a.endpoints)},
        )
    else:
        named = naive if base == "naive" else base
        if not named:
            raise ValueError("Comparing against the naive architecture names it: pass its id as naive.")
        selected = store.require(named)
        if selected.id == candidate.id or selected.id in descendants(candidate.id, store.list()):
            raise ValueError("Select the model or a different candidate outside this candidate's descendants.")
        before = read_view(selected, store, registry)
    return to_jsonable_python({
        "candidate": candidate.id, "base": base, "stack": [layer.id for layer in stack],
        "view": after.wire(), "diff": difference(before, after),
        "standing": _standing(candidate, stack, live),
    })


def reading_beneath(
    candidate: CandidateArchitecture, store: CandidateLookup, registry: ArtifactRegistry, also: Iterable[str] = (),
) -> ModelReading:
    """What *candidate*'s operations are written against: the model with the stack beneath it laid over."""
    stack = stack_of(candidate, store.find)
    live = live_reading(stack, registry, also)
    return compose(ChangeSet((), candidate.changes.repository_revision), live, beneath=sets_beneath(stack))


def rebase(
    candidate: CandidateArchitecture, store: CandidateLookup, registry: ArtifactRegistry, revision: str,
) -> CandidateArchitecture:
    """*candidate* with every drifted operation written again against the model at *revision*.

    Which operations drifted is standing's to say, read here exactly as `standing_report` reads it; a
    conflicting one has nothing to apply to and is left for its author, with its reason, to drop.
    """
    stack = stack_of(candidate, store.find)
    live = live_reading(stack, registry)
    beneath = sets_beneath(stack)
    drifted = [item.operation for item in standing_of(candidate.changes, live, beneath=beneath)
               if item.standing == "drifted"]
    if not drifted:
        return candidate
    now = rebased(candidate, drifted, compose(ChangeSet((), revision), live, beneath=beneath))
    return replace(now, changes=ChangeSet(now.changes.operations, revision))


def standing_report(
    candidate: CandidateArchitecture, store: CandidateLookup, registry: ArtifactRegistry,
) -> list[dict[str, Any]]:
    """Where each of the candidate's own operations stands on the model as it is now."""
    stack = stack_of(candidate, store.find)
    return _standing(candidate, stack, live_reading(stack, registry))


def _standing(
    candidate: CandidateArchitecture, stack: tuple[CandidateArchitecture, ...], live: RecordedReading,
) -> list[dict[str, Any]]:
    return wire_standing(standing_of(candidate.changes, live, beneath=sets_beneath(stack)))


def wire_standing(standing: Iterable[OperationStanding]) -> list[dict[str, Any]]:
    """Each operation's standing as the transports answer it: the operation, its position, the reason."""
    return to_jsonable_python([
        {"operation": operation_to_mapping(item.operation), "standing": item.standing, "reason": item.reason}
        for item in standing
    ])
