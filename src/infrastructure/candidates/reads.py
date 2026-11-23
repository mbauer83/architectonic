"""Compose candidate reads over current scoped records from the repository index."""
from __future__ import annotations

from typing import Any

from pydantic_core import to_jsonable_python

from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.candidate_view import CandidateView, difference, view_of
from src.application.change_sets.operations import ConnectionAddress, CreateEntity
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.recorded_form import operation_to_mapping
from src.application.change_sets.stacking import descendants, sets_beneath, stack_of
from src.application.change_sets.standing import standing_of
from src.application.modeling.edit_field_values import current_entity_values
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.artifact_id import canonical_entity_key
from src.infrastructure.candidates.repository import CandidateRepository


def live_reading(stack: tuple[CandidateArchitecture, ...], registry: ArtifactRegistry) -> RecordedReading:
    refs = {ref for layer in stack for ref in layer.scope}
    for layer in stack:
        for operation in layer.changes.operations:
            subject = operation.claim.subject
            refs.update(subject.endpoints if isinstance(subject, ConnectionAddress) else (subject,))
            if isinstance(operation, CreateEntity) and operation.artifact_id:
                refs.add(operation.artifact_id)
    entities, relations = {}, {}
    aliases = {}
    for ref in sorted(refs):
        if (entity := registry.get_entity(ref)) is not None:
            entities[ref] = dict(current_entity_values(entity), artifact_type=entity.artifact_type)
            aliases[canonical_entity_key(entity.artifact_id)] = ref
    for ref in entities:
        for conn in registry.find_connections_for(ref):
            address = ConnectionAddress(aliases.get(canonical_entity_key(conn.source), conn.source), conn.conn_type,
                                        aliases.get(canonical_entity_key(conn.target), conn.target))
            relations[address] = {
                "description": conn.content_text, "metadata": dict(conn.attributes),
                "specializations": conn.specializations,
                "src_multiplicity": conn.src_multiplicity, "tgt_multiplicity": conn.tgt_multiplicity,
            }
    return RecordedReading(entities, relations)


def read_view(
    candidate: CandidateArchitecture, store: CandidateRepository, registry: ArtifactRegistry,
) -> CandidateView:
    stack = stack_of(candidate, store.find)
    return view_of(stack, live_reading(stack, registry))


def comparison(
    candidate: CandidateArchitecture, store: CandidateRepository, registry: ArtifactRegistry,
    *, base: str, naive: str | None,
) -> dict[str, Any]:
    stack = stack_of(candidate, store.find)
    live = live_reading(stack, registry)
    after = view_of(stack, live)
    if base == "model":
        refs = set(live.entities)
        before = CandidateView(
            {ref: fields for ref, fields in live.entities.items() if ref in refs},
            {a: f for a, f in live.connections.items() if all(end in refs for end in a.endpoints)},
        )
    else:
        selected = naive if base == "naive" else base
        if not selected or selected == candidate.id or selected in descendants(candidate.id, store.list()):
            raise ValueError("Select the model or a different candidate outside this candidate's descendants.")
        before = read_view(store.require(selected), store, registry)
    return to_jsonable_python({
        "candidate": candidate.id, "base": base, "stack": [layer.id for layer in stack],
        "view": after.wire(), "diff": difference(before, after),
        "standing": [
            {"operation": operation_to_mapping(item.operation), "standing": item.standing, "reason": item.reason}
            for item in standing_of(candidate.changes, live, beneath=sets_beneath(stack))
        ],
    })
