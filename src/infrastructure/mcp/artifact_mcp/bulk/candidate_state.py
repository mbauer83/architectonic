"""Construct the staged read view for an MCP batch."""

from pathlib import Path

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.write.artifact_write.candidate_state import CandidateStore


def candidate_registry(*, live_root: Path, staged_root: Path, touched_paths: set[Path]) -> ArtifactRegistry:
    return ArtifactRegistry(candidate_store(live_root=live_root, staged_root=staged_root, touched_paths=touched_paths))


def candidate_store(*, live_root: Path, staged_root: Path, touched_paths: set[Path]) -> CandidateStore:
    from src.infrastructure.app_bootstrap import process_runtime_catalogs
    from src.infrastructure.artifact_index import mutable_artifact_index

    domain_names = process_runtime_catalogs().ontology.known_domain_names()
    return CandidateStore(
        live=mutable_artifact_index(live_root),
        live_root=live_root,
        staged_root=staged_root,
        touched_paths=touched_paths,
        domain_names=domain_names,
    )
