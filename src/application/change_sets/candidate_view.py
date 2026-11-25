"""Scoped entities and relations as the model or a stack of candidates describes them."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.application.change_sets.candidate_architecture import CandidateArchitecture
from src.application.change_sets.composition import compose
from src.application.change_sets.operations import ConnectionAddress
from src.application.change_sets.reading import FieldValues, RecordedReading
from src.application.change_sets.stacking import sets_beneath
from src.domain.artifact_id import canonical_entity_key


@dataclass(frozen=True)
class CandidateView:
    entities: dict[str, FieldValues]
    connections: dict[ConnectionAddress, FieldValues]
    #: The id chosen for each entity the stack creates, by the reference the view names it with.
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
    reading = compose(stack[-1].changes, live, beneath=sets_beneath(stack))
    references = {canonical_entity_key(ref) for layer in stack for ref in layer.scope} | set(reading.entities)
    entities = {ref: fields for ref in references if (fields := reading.entity(ref)) is not None}
    addresses = live.connections.keys() | reading.connections.keys()
    connections = {
        address: fields for address in addresses
        if all(ref in entities for ref in address.endpoints) and (fields := reading.connection(address)) is not None
    }
    chosen = {
        ref: create.artifact_id for layer in stack for ref, create in layer.changes.created.items()
        if ref in entities and create.artifact_id
    }
    return CandidateView(entities, connections, chosen)


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
