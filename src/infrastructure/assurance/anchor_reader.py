"""Reads the architecture model to describe a prospective signal anchor.

The adapter behind the ``AnchorReader`` port. The dependency runs assurance →
architecture, which is the direction the codebase already establishes: assurance
reads and references architecture through ports (``ArchitectureEntityCreator`` in
model-and-bind, the one-way arch references); architecture never depends on
assurance.

Resolution goes through the index's own canonical-id handling, so either anchor id
form resolves — the same normalization ``anchor_key`` applies on the storage side.
The index spans BOTH repositories where an enterprise repo is configured, so an
anchor promoted to enterprise still resolves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from src.domain.assurance.security_signal_snapshot import AnchorDescriptor


class EntityLookup(Protocol):
    """The slice of the artifact index this adapter needs."""

    def get_entity(self, artifact_id: str) -> Any: ...


class IndexAnchorReader:
    """Describes anchors from an artifact index."""

    def __init__(self, index: EntityLookup) -> None:
        self._index = index

    def describe_anchor(self, entity_id: str) -> AnchorDescriptor | None:
        entity = self._index.get_entity(entity_id)
        if entity is None:
            return None
        return AnchorDescriptor(
            entity_id=str(entity.artifact_id),
            artifact_type=str(entity.artifact_type),
            specialization=str(getattr(entity, "specialization", "") or ""),
        )


class UnavailableAnchorReader:
    """Used when no architecture index can be resolved.

    Reports every anchor as unknown, so an ingest FAILS rather than silently
    skipping validation. Degrading to "allow everything" when the model cannot be
    consulted would make the check advisory exactly when it is least verifiable.
    """

    def describe_anchor(self, entity_id: str) -> AnchorDescriptor | None:
        return None


def anchor_reader_for(repo_root: Path | None = None) -> IndexAnchorReader | UnavailableAnchorReader:
    """Build the reader for the current workspace.

    Prefers the combined engagement+enterprise index, matching what every other
    read surface resolves against.
    """
    from src.config.workspace_paths import resolve_workspace_repo_roots  # noqa: PLC0415
    from src.infrastructure.artifact_index import (  # noqa: PLC0415
        combined_artifact_index,
        shared_artifact_index,
    )

    roots = resolve_workspace_repo_roots(repo_root or Path.cwd())
    if roots is None:
        if repo_root is None:
            return UnavailableAnchorReader()
        return IndexAnchorReader(shared_artifact_index(repo_root))
    engagement, enterprise = roots
    return IndexAnchorReader(combined_artifact_index(engagement, enterprise))
