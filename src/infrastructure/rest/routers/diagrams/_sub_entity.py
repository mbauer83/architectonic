"""Reading one construct a diagram owns, at the diagram's own address.

Its own module for the same reason the palette, the context and the writes have theirs: this router
is an aggregator, and a surface added inline pushes it past the module-size limit in `STD@1777137196`
without anyone deciding to.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.application._diagram_entity_extraction import NOTHING_HELD, extract_diagram_entities
from src.application.artifacts._query_helpers import read_entity as serialize_entity
from src.application.artifacts.parsing import parse_entity_content_sections
from src.application.modeling.proposal_standing import standing_subject
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification._verifier_contribution_runner import held_record_scopes_from_catalogs
from src.domain.baseline_standing import BASELINE_STANDING
from src.infrastructure.rest.contracts.entities import EntityDetailResponse
from src.infrastructure.rest.dependencies import runtime_catalogs_dependency
from src.infrastructure.rest.routers import state as s
from src.infrastructure.rest.routers._openapi import READ_RESPONSES, TAG_DIAGRAMS

router = APIRouter()


@router.get(
    "/api/diagrams/{artifact_id}/entities/{entity_type}/{local_id}",
    tags=[TAG_DIAGRAMS],
    summary="Read one diagram-owned construct",
    response_model=EntityDetailResponse,
    response_model_exclude_none=True,
    responses=READ_RESPONSES,
)
def get_diagram_entity(
    artifact_id: str,
    entity_type: str,
    local_id: str,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    """A construct the diagram owns — a GSN goal, a swimlane — at the diagram's own address.

    These are sub-entities of the diagram, and this is where they are addressed. They cannot be read
    through the flat entity collection: their identifier is ``{diagram_id}#{entity_type}/{local_id}``
    (``_diagram_entity_extraction.py``), so it contains a slash, and a slash in a path parameter ends
    the segment — an encoded one is decoded back by the server before routing, so
    ``/api/entities/GSN@…%23nodes%2Fg11`` does not match that route at all and answers 404.

    Splitting the two composite parts into two segments is what removes the slash from any single
    identifier, and it also says what was true all along: the type and the local id are the diagram's
    coordinates for something inside it, not an opaque global id that happens to contain punctuation.
    """
    # Resolved from the diagram's own constructs, not through the entity read. `read_artifact` maps a
    # composite id to its *host diagram* — so asking it for `…#nodes/g11` returns the diagram, a
    # different resource with a different record type, which only a closed response contract reveals.
    # The diagram is already in hand here, and its constructs are the authoritative list.
    repo = s.get_repo()
    diagram = repo.get_diagram(artifact_id)
    if diagram is None:
        raise HTTPException(404, f"Diagram not found: {artifact_id!r}")
    wanted = f"{artifact_id}#{entity_type}/{local_id}"
    record = next(
        (entity for entity in extract_diagram_entities(
            diagram, held_record_scopes_from_catalogs(catalogs).get(diagram.diagram_type, NOTHING_HELD),
        ) if entity.artifact_id == wanted),
        None,
    )
    if record is None:
        raise HTTPException(404, f"Not found on {artifact_id!r}: {entity_type}/{local_id}")
    detail = serialize_entity(record, mode="full")
    parsed = parse_entity_content_sections(record.content_text)
    detail["summary"] = parsed["summary"]
    detail["properties"] = parsed["properties"]
    detail["notes"] = parsed["notes"]
    detail["is_global"] = s.is_global(record.path)
    detail[BASELINE_STANDING] = s.baseline_standing_reader()(standing_subject(record)).to_mapping()
    return detail
