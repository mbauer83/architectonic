"""Where an entity is referred to: the documents that link to it, and the diagrams that draw it.

One question with two halves, assembled in one place because it was already assembled twice. The
document half was built at both the read-artifact path and the REST entity-context path, in two copies
of the same two lines; adding the diagram half would have made four. A reader of an entity's page
wants "where does this appear", not two independently-maintained lists.

**The two halves are answered differently, and that is not an inconsistency.** A document reference
carries *where inside* the document the link sits — a section and an href — so it is found by reading
the documents' own links, which is what `document_links` owns. A diagram either draws the entity or it
does not, and the index already keeps that reverse mapping, so it is a lookup. Making the diagram half
scan every diagram to look symmetric would be slower and no truer.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from src.application.document_links import reference_dicts_for_entity
from src.domain.ontology_representation.artifact_types import DiagramRecord, DocumentRecord, EntityRecord


class ReferenceSource(Protocol):
    """What answering the question needs. Both the store and the repository facade satisfy it."""

    def list_documents(self, **kwargs: Any) -> list[DocumentRecord]: ...

    def diagrams_referencing_artifact(self, artifact_id: str) -> list[DiagramRecord]: ...


def diagram_reference_dicts(diagrams: Iterable[DiagramRecord]) -> list[dict[str, str]]:
    """The diagrams that draw an entity, as a display surface reads them.

    Name and type travel with the id because a reader choosing between "Resource Investment Map" and
    "Capability Map" is choosing by name, and a page that showed ids would make them open both.

    Keyed `artifact_id`, which is what every other record on this surface calls its id and what the
    one `DiagramReference` DTO declares — the same rows answer "which diagrams draw this pair".
    """
    return [
        {
            "artifact_id": diagram.artifact_id,
            "name": diagram.name,
            "diagram_type": diagram.diagram_type,
            "status": diagram.status,
        }
        for diagram in sorted(diagrams, key=lambda d: (d.name.lower(), d.artifact_id))
    ]


def references_to(entity: EntityRecord, source: ReferenceSource) -> dict[str, Sequence[dict[str, str]]]:
    """Both halves, keyed as the entity contract names them."""
    return {
        "referenced_in_documents": reference_dicts_for_entity(
            documents=source.list_documents(), entity=entity
        ),
        "referenced_in_diagrams": diagram_reference_dicts(
            source.diagrams_referencing_artifact(entity.artifact_id)
        ),
    }
