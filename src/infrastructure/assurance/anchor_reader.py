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
    """Build the reader for the repository this process is serving.

    Prefers the combined engagement+enterprise index, matching what every other
    read surface resolves against.

    **Which repository, resolved the way the server resolved it.** This used to ask
    `resolve_workspace_repo_roots(Path.cwd())` and nothing else, so the model consulted
    was whatever workspace happened to lie at or above the working directory. That is
    not a wrong answer but a refusal: with no workspace there, `UnavailableAnchorReader`
    reports every anchor as unknown — deliberately, so an ingest fails rather than
    skipping validation — and an ingest naming an entity that plainly exists was told
    "no architecture entity exists". It bit a container, a service manager, and a
    backend serving a generated fixture repository, all of which set `ARCH_REPO_ROOT`
    and none of which run from the workspace.

    `resolve_server_roots` is asked rather than the environment being read here,
    because it is where the precedence — explicit argument, then environment, then
    arch-init state — is already defined, and a second copy of a precedence rule is a
    second thing to drift. Its answer is what `arch-backend` served, so the anchors
    this validates against are the entities that backend would return.

    cwd-based discovery stays as the last resort: a developer running from inside a
    workspace with nothing configured still gets the workspace they are standing in.
    """
    from src.config.workspace_paths import resolve_workspace_repo_roots  # noqa: PLC0415
    from src.infrastructure.artifact_index import (  # noqa: PLC0415
        combined_artifact_index,
        shared_artifact_index,
    )
    from src.infrastructure.backend.server_roots import resolve_server_roots  # noqa: PLC0415

    configured_engagement, configured_enterprise = resolve_server_roots(
        str(repo_root) if repo_root is not None else None, None
    )
    if configured_engagement is not None:
        if configured_enterprise is not None:
            return IndexAnchorReader(
                combined_artifact_index(configured_engagement, configured_enterprise)
            )
        return IndexAnchorReader(shared_artifact_index(configured_engagement))

    roots = resolve_workspace_repo_roots(repo_root or Path.cwd())
    if roots is None:
        if repo_root is None:
            return UnavailableAnchorReader()
        return IndexAnchorReader(shared_artifact_index(repo_root))
    engagement, enterprise = roots
    return IndexAnchorReader(combined_artifact_index(engagement, enterprise))
