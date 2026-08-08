from __future__ import annotations

from typing import Any, cast

from src.application.document_links import references_to_entity
from src.domain.ontology_representation.artifact_types import DiagramRecord, DocumentRecord, EntityRecord

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

    def documents_referencing_entity(self, artifact_id: str) -> list[DocumentRecord]:
        """Documents linking to this entity's file.

        Read from the documents themselves rather than from an index: a document's reference is a
        markdown link in its prose, not a modelled relation, and `references_to_entity` is where
        that reading already lives — the entity context and the repository read both use it.
        """
        owner = cast(Any, self)
        owner._ensure_loaded()
        with owner._lock.reading():
            entity = owner._mem.entities.get(artifact_id)
            if entity is None:
                return []
            documents = list(owner._mem.documents.values())
        referencing = {ref.document_id for ref in references_to_entity(documents=documents, entity=entity)}
        return sorted((d for d in documents if d.artifact_id in referencing), key=lambda d: d.artifact_id)
