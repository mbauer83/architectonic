from __future__ import annotations

from pathlib import Path

from src.application.ports import ArtifactStorePort, ReadableArtifactStore
from src.domain.ontology_representation.artifact_types import RepoMount

from .bootstrap import get_combined_index, get_shared_index, normalize_mounts
from .service import ArtifactIndex


def combined_artifact_index(engagement_root: Path, enterprise_root: Path) -> ReadableArtifactStore:
    return get_combined_index(ArtifactIndex, engagement_root, enterprise_root)


def mutable_artifact_index(repo_root: Path) -> ArtifactStorePort:
    return get_shared_index(ArtifactIndex, repo_root)


def shared_artifact_index(repo_root: Path | list[Path] | list[RepoMount]) -> ReadableArtifactStore:
    mounts = normalize_mounts(repo_root)
    if len(mounts) != 2:
        return get_shared_index(ArtifactIndex, mounts)
    engagement = next((m.root for m in mounts if m.scope == "engagement"), mounts[0].root)
    enterprise = next((m.root for m in mounts if m.scope == "enterprise"), mounts[1].root)
    if engagement == enterprise:
        raise ValueError("Combined artifact index requires distinct engagement and enterprise roots")
    return combined_artifact_index(engagement, enterprise)
