"""What reading a picture needs of the repository a transport serves, handed in rather than looked up."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.application.artifacts.query import ArtifactRepository
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord


@dataclass(frozen=True)
class PictureSources:
    """The served repository, its catalogues, and how the transport lists an element or a relation.

    *registry* is asked only by a reading that resolves what a diagram places, so a transport building one
    over both tiers pays for it only then. *entity_row* and *connection_row* are the transport's own rows
    for an element and a relation, so a picture's context lists them as every other read of that transport
    does.
    """

    repo: ArtifactRepository
    catalogs: RuntimeCatalogs
    repo_root: Path | None
    registry: Callable[[], ArtifactRegistry]
    entity_row: Callable[[EntityRecord], dict[str, Any]]
    connection_row: Callable[[ConnectionRecord], dict[str, Any]]
