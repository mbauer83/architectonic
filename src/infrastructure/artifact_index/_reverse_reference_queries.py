from __future__ import annotations

from typing import Any, cast

from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord

_EntityIds = list[str] | set[str] | frozenset[str]


class _ReverseReferenceQueries:
    def diagrams_referencing_artifact(self, artifact_id: str) -> list[DiagramRecord]:
        owner = cast(Any, self)
        owner._ensure_loaded()
        with owner._lock.reading():
            refs = owner._mem.diagrams_by_reference.get(artifact_id, set())
            return sorted((r for did in refs if (r := owner._mem.diagrams.get(did))), key=lambda r: r.artifact_id)

    def grf_references_to_entity(self, artifact_id: str) -> list[EntityRecord]:
        owner = cast(Any, self)
        owner._ensure_loaded()
        with owner._lock.reading():
            refs = owner._mem.grf_targets_by_entity.get(artifact_id, set())
            return sorted((r for eid in refs if (r := owner._mem.entities.get(eid))), key=lambda r: r.artifact_id)
