"""What a candidate's editor reads about the picture it sketches on (`candidates.picture`)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from src.infrastructure.rest.contracts.diagram_groupings import AuthoredGroupingResponse
from src.infrastructure.rest.contracts.diagrams import (
    DerivedViewEntityResponse,
    DiagramContextConnection,
    DiagramContextEntity,
    HopSuggestionGroup,
)
from src.infrastructure.rest.contracts.entities import ContextConnection
from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


class PictureStartResponse(NullsOmitted):
    """Where the picture starts, as a diagram's editor reads what a diagram draws."""

    artifact_id: str = Field(
        description="The stored diagram the picture starts from; empty where it starts from a generated view.",
    )
    name: str
    diagram_type: str
    entity_ids_used: list[str] | None = Field(None, description="The model's entities the start draws.")
    connection_ids_used: list[str] | None = Field(None, description="The model's relations the start draws.")
    diagram_entities: dict[str, Any] | None = None
    authored_groupings: list[AuthoredGroupingResponse] | None = None
    #: Frontmatter the diagram read does not model, as written (a stored start's own connections, say).
    extra: dict[str, Any] | None = None


class CandidatePictureContext(NullsOmitted):
    """A candidate's picture and everything its editor needs, in one read, as a diagram's context read answers
    for a diagram: what the start draws, what the model relates it to, and what lies one and two steps away
    from it and from every element the candidate reads over."""

    diagram: PictureStartResponse
    entities: list[DiagramContextEntity]
    connections: list[DiagramContextConnection]
    drawn_labels: dict[str, str]
    candidate_connections: list[ContextConnection]
    suggested_entities: list[HopSuggestionGroup]
    explicit_connection_pairs: list[tuple[str, str]]
    generation: int
    etag: str
    type_extras: dict[str, Any] | None = None
    derived_entities: list[DerivedViewEntityResponse] | None = None
