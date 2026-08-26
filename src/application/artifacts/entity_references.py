"""Where an entity is referred to: the documents that link to it, the diagrams that draw it, and the
scratchpads whose notes point at it.

One question with three halves, assembled in one place because it was already assembled twice. The
document half was built at both the read-artifact path and the REST entity-context path, in two copies
of the same two lines; each further kind would have doubled again. A reader of an entity's page wants
"where does this appear", not three independently-maintained lists — and it is what gives MCP the same
answer as the GUI for free, since `read_artifact` and the entity context now ask the same function.

**The kinds are answered differently, and that is not an inconsistency.** A document reference carries
*where inside* the document the link sits — a section and an href — so it is found by reading the
documents' own links, which is what `document_links` owns. A diagram either draws the entity or does
not, and a scratchpad note either holds a `model_ref` to it or does not; the index keeps a reverse map
for both, so both are lookups. Making either scan every artifact to look symmetric with the document
half would be slower and no truer.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from src.application.document_links import reference_dicts_for_entity
from src.domain.ontology_representation.artifact_types import (
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadRecord,
)


class ReferenceSource(Protocol):
    """What answering the question needs. Both the store and the repository facade satisfy it."""

    def list_documents(self, **kwargs: Any) -> list[DocumentRecord]: ...

    def diagrams_referencing_artifact(self, artifact_id: str) -> list[DiagramRecord]: ...

    def scratchpads_referencing_artifact(self, artifact_id: str) -> list[ScratchpadRecord]: ...


def _by_name(record: DiagramRecord | ScratchpadRecord) -> tuple[str, str]:
    """How a reference list is ordered: by name, then by id to break a tie.

    Named once because both lists follow it. A reader choosing between two references chooses by name,
    and a list that reorders between reads is one they cannot scan twice — so the id is the tiebreak
    rather than the sort, and two artifacts sharing a name still come back in a fixed order.
    """
    return (record.name.lower(), record.artifact_id)


def diagram_reference_dicts(diagrams: Iterable[DiagramRecord]) -> list[dict[str, str]]:
    """The diagrams that draw an entity, as a display surface reads them.

    Name and type travel with the id because a reader choosing between two diagrams is choosing by
    name, and a page that showed ids would make them open both.

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
        for diagram in sorted(diagrams, key=_by_name)
    ]


def scratchpad_reference_dicts(scratchpads: Iterable[ScratchpadRecord]) -> list[dict[str, str]]:
    """The scratchpads whose notes point at an entity, as a display surface reads them.

    A pad rather than a note, and that is the whole shape of the answer: a note holding a model
    reference stops being a searchable record at all — the model then answers for that thought — so
    the pad is both what survives and what a reader navigates to.
    """
    return [
        {
            "artifact_id": pad.artifact_id,
            "name": pad.name,
            "status": pad.status,
        }
        for pad in sorted(scratchpads, key=_by_name)
    ]


def references_to(entity: EntityRecord, source: ReferenceSource) -> dict[str, Sequence[dict[str, str]]]:
    """Every kind, keyed as the entity contract names them."""
    return {
        "referenced_in_documents": reference_dicts_for_entity(
            documents=source.list_documents(), entity=entity
        ),
        "referenced_in_diagrams": diagram_reference_dicts(
            source.diagrams_referencing_artifact(entity.artifact_id)
        ),
        "referenced_in_scratchpads": scratchpad_reference_dicts(
            source.scratchpads_referencing_artifact(entity.artifact_id)
        ),
    }
