"""Application-layer query facade."""

from src.application.artifact_repository import ArtifactRepository
from src.domain.ontology_representation.artifact_types import (
    ArtifactSummary,
    ConnectionRecord,
    DiagramRecord,
    DuplicateArtifactIdError,
    EntityRecord,
    RepoMount,
    SearchHit,
    SearchResult,
    SemanticSearchProvider,
)

__all__ = [
    "ArtifactSummary",
    "ConnectionRecord",
    "DiagramRecord",
    "DuplicateArtifactIdError",
    "EntityRecord",
    "ArtifactRepository",
    "RepoMount",
    "SearchHit",
    "SearchResult",
    "SemanticSearchProvider",
]
