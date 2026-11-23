"""Construct the staged read view for an MCP batch."""

from pathlib import Path

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.write.artifact_write.staged_state import StagedStore


def staged_registry(*, live_root: Path, staged_root: Path, touched_paths: set[Path]) -> ArtifactRegistry:
    return ArtifactRegistry(staged_store(live_root=live_root, staged_root=staged_root, touched_paths=touched_paths))


def staged_store(*, live_root: Path, staged_root: Path, touched_paths: set[Path]) -> StagedStore:
    from src.infrastructure.app_bootstrap import process_runtime_catalogs
    from src.infrastructure.artifact_index import mutable_artifact_index

    domain_names = process_runtime_catalogs().ontology.known_domain_names()
    return StagedStore(
        live=mutable_artifact_index(live_root),
        live_root=live_root,
        staged_root=staged_root,
        touched_paths=touched_paths,
        domain_names=domain_names,
    )
