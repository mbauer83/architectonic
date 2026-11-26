"""Scoped entities and relations as the model or a stack of candidates describes them.

A view is an answer, so it names every entity as a caller does (`created_names`): one the stack creates
by the stable form of the id its create chose, never by the alias its operations name it with.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.composition import ComposedReading, compose
from src.application.change_sets.created_names import ChosenIds, chosen_ids, reference_for, spoken
from src.application.change_sets.operations import ConnectionAddress
from src.application.change_sets.reading import FieldValues, RecordedReading
from src.application.change_sets.stacking import sets_beneath
from src.domain.artifact_id import canonical_entity_key
from src.domain.provisional_reference import provisional


@dataclass(frozen=True)
class CandidateView:
    entities: dict[str, FieldValues]
    connections: dict[ConnectionAddress, FieldValues]
    #: The id chosen for each entity the stack creates, as its create states it, by the id the view names it with.
    chosen: dict[str, str] = field(default_factory=dict)

    def wire(self) -> dict[str, Any]:
        return {
            "entities": [
                {"id": ref, "fields": fields, **({"artifact_id": self.chosen[ref]} if ref in self.chosen else {})}
                for ref, fields in sorted(self.entities.items())
            ],
            "connections": [
                {**asdict(address), "fields": fields}
                for address, fields in sorted(self.connections.items(), key=lambda pair: str(pair[0]))
            ],
        }


def view_of(stack: tuple[CandidateArchitecture, ...], live: RecordedReading) -> CandidateView:
    """What *stack* describes over the *live* model: its scope and what its operations touch.

    An entity the stack creates is one entity whether or not the model holds it yet: once the id chosen for it
    is in the model (applied as a target state, say), the model's record and the create are read as one, under
    the reference the operations name it with (`named_by_reference`), with what the create states over what
    the model holds. The view answers it by that id.
    """
    reading = compose(stack[-1].changes, live, beneath=sets_beneath(stack))
    chosen = chosen_ids(layer.changes for layer in stack)
    named = named_by_reference(live, chosen)
    created = {provisional(alias) for alias in chosen}
    held = {canonical_entity_key(artifact_id) for artifact_id in chosen.values()}
    references = {canonical_entity_key(ref) for layer in stack for ref in layer.scope} | set(reading.entities)
    entities = {
        ref: {**(named.entity(ref) or {}), **fields} if ref in created else fields
        for ref in {reference_for(ref, chosen) for ref in references} - held
        if (fields := reading.entity(ref)) is not None
    }
    addresses = named.connections.keys() | reading.connections.keys()
    connections = {
        address: fields for address in addresses
        if all(ref in entities for ref in address.endpoints)
        and (fields := _connection(address, reading, named)) is not None
    }
    return _named_by_id(CandidateView(entities, connections), {
        alias: artifact_id for alias, artifact_id in chosen.items() if provisional(alias) in entities
    })


def _named_by_id(view: CandidateView, chosen: Mapping[str, str]) -> CandidateView:
    """*view*, read under the stack's references, with each entity the stack creates named by its id."""
    def name(ref: str) -> str:
        return spoken(ref, chosen)

    return CandidateView(
        {name(ref): fields for ref, fields in view.entities.items()},
        {
            ConnectionAddress(name(a.source_entity), a.connection_type, name(a.target_entity)): fields
            for a, fields in view.connections.items()
        },
        chosen={canonical_entity_key(artifact_id): artifact_id for artifact_id in chosen.values()},
    )


def named_by_reference(live: RecordedReading, chosen: ChosenIds) -> RecordedReading:
    """*live*, with each record the model holds under an id a create chose named by that create's reference
    (`reference_for`), so the model's reading and the stack's name the same entity alike."""
    def name(ref: str) -> str:
        return reference_for(ref, chosen)

    return RecordedReading(
        {name(ref): fields for ref, fields in live.entities.items()},
        {
            ConnectionAddress(name(a.source_entity), a.connection_type, name(a.target_entity)): fields
            for a, fields in live.connections.items()
        },
    )


def _connection(address: ConnectionAddress, reading: ComposedReading, named: RecordedReading) -> FieldValues | None:
    """What the stack says of *address*, else what the model says of it under the stack's names."""
    if address in reading.connections or address not in named.connections:
        return reading.connection(address)
    return named.connection(address)


def difference(before: CandidateView, after: CandidateView) -> list[dict[str, Any]]:
    return [
        *_changes("entity", before.entities, after.entities),
        *_changes("connection", before.connections, after.connections),
    ]


def _changes[K](kind: str, left: dict[K, FieldValues], right: dict[K, FieldValues]) -> list[dict[str, Any]]:
    changes = []
    for key in sorted(left.keys() | right.keys(), key=str):
        old, new = left.get(key), right.get(key)
        if old == new:
            continue
        original, proposed = old or {}, new or {}
        fields = {
            field: {"before": original.get(field), "after": proposed.get(field)}
            for field in sorted(original.keys() | proposed.keys())
            if field not in original or field not in proposed or original[field] != proposed[field]
        }
        changes.append({
            "kind": kind, "target": asdict(key) if isinstance(key, ConnectionAddress) else key,
            "change": "added" if old is None else "removed" if new is None else "edited", "fields": fields,
        })
    return changes
