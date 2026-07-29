"""Structural-closure preflight for promotion: entities with no standalone meaning.

A junction IS its incident connection set (AND/OR over branches) and a grouping IS its
membership — promoting either without the entities that give it meaning silently mutates
semantics: connections to non-promoted endpoints are dropped enterprise-side, and the
engagement original becomes a global reference that cannot carry directed outgoing
edges, so the structure is not left behind but erased. The plan therefore BLOCKS
(mirroring the datatype type-closure precedent) instead of auto-widening the caller's
explicit selection — promotion stays a reviewed, explicitly-selected set.

The requirements are STRUCTURED (which anchor entity, which entities are missing, with
names) so surfaces can offer a one-action "include the missing entities" flow; the prose
``schema_errors`` derived from them keep non-GUI callers blocked with the same facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.application.artifact_repository import ArtifactRepository

_GROUPING_TYPE = "grouping"
_MEMBERSHIP_CONNECTION_TYPES = frozenset({"archimate-composition", "archimate-aggregation"})

ClosureKind = Literal["junction", "grouping"]


@dataclass(frozen=True)
class ClosureEntity:
    """One entity a closure requirement is missing — named so surfaces can render it."""

    artifact_id: str
    name: str
    artifact_type: str


@dataclass(frozen=True)
class StructuralClosureRequirement:
    """One selected junction/grouping whose meaning-carrying entities are missing."""

    entity_id: str
    entity_name: str
    kind: ClosureKind
    missing: tuple[ClosureEntity, ...]


def _is_junction_type(entity_type: str) -> bool:
    return entity_type == "junction" or entity_type.endswith("-junction")


def _closure_entity(repo: ArtifactRepository, entity_id: str) -> ClosureEntity:
    record = repo.get_entity(entity_id)
    if record is None:
        return ClosureEntity(artifact_id=entity_id, name=entity_id, artifact_type="")
    return ClosureEntity(artifact_id=entity_id, name=record.name, artifact_type=record.artifact_type)


def _junction_required_endpoints(
    repo: ArtifactRepository, junction_id: str, seen_junctions: set[str]
) -> set[str]:
    """All non-junction endpoints incident to *junction_id*, transitively through
    junction chains — the complete set a junction's meaning rests on."""
    seen_junctions.add(junction_id)
    required: set[str] = set()
    for connection in repo.find_connections_for(junction_id, direction="any"):
        for endpoint in (connection.source, connection.target):
            if endpoint == junction_id or endpoint in seen_junctions:
                continue
            record = repo.get_entity(endpoint)
            if record is not None and _is_junction_type(record.artifact_type):
                required |= _junction_required_endpoints(repo, endpoint, seen_junctions)
                required.add(endpoint)
            else:
                required.add(endpoint)
    return required


def _grouping_members(repo: ArtifactRepository, grouping_id: str) -> set[str]:
    return {
        connection.target
        for connection in repo.find_connections_for(grouping_id, direction="outbound")
        if connection.conn_type in _MEMBERSHIP_CONNECTION_TYPES
    }


def compute_structural_closure(
    promoted_entity_ids: set[str],
    *,
    repo: ArtifactRepository,
    enterprise_ids: set[str],
) -> list[StructuralClosureRequirement]:
    """Closure requirements for selected junctions/groupings whose meaning-carrying
    entities are neither in the selection nor already enterprise-side. A GAR endpoint
    counts as satisfied — it already stands for a global entity."""

    def satisfied(entity_id: str) -> bool:
        return (
            entity_id in promoted_entity_ids
            or entity_id in enterprise_ids
            or entity_id.startswith("GAR@")
        )

    requirements: list[StructuralClosureRequirement] = []
    for entity_id in sorted(promoted_entity_ids):
        record = repo.get_entity(entity_id)
        if record is None:
            continue
        if _is_junction_type(record.artifact_type):
            kind: ClosureKind = "junction"
            required = _junction_required_endpoints(repo, entity_id, set())
        elif record.artifact_type == _GROUPING_TYPE:
            kind = "grouping"
            required = _grouping_members(repo, entity_id)
        else:
            continue
        missing = tuple(
            _closure_entity(repo, required_id)
            for required_id in sorted(required)
            if not satisfied(required_id)
        )
        if missing:
            requirements.append(
                StructuralClosureRequirement(
                    entity_id=entity_id, entity_name=record.name, kind=kind, missing=missing
                )
            )
    return requirements


def structural_closure_errors(requirements: list[StructuralClosureRequirement]) -> list[str]:
    """Blocking prose for the same facts — non-GUI callers get actionable messages."""
    errors: list[str] = []
    for requirement in requirements:
        missing_ids = ", ".join(entity.artifact_id for entity in requirement.missing)
        if requirement.kind == "junction":
            errors.append(
                f"Broken structural closure: junction {requirement.entity_id} has no meaning apart "
                f"from its complete connection set — add its connected entities to the promotion "
                f"selection: {missing_ids}"
            )
        else:
            errors.append(
                f"Broken structural closure: grouping {requirement.entity_id} would be promoted "
                f"without its contents, erasing the membership edges — add its members to the "
                f"promotion selection: {missing_ids}"
            )
    return errors
