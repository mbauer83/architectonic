"""Regression coverage for the ArtifactMutationObserver-omission design:
`CombinedArtifactView` must structurally satisfy
`ReadableArtifactStore` (no `cast`), `ArtifactRepository` must accept it without narrowing
tricks, and the two now-dead `apply_file_change(s)` pass-through methods must actually be gone
— not just unused.
"""

from __future__ import annotations

from pathlib import Path

from src.application.artifact_repository import ArtifactRepository
from src.application.ports import ReadableArtifactStore
from src.infrastructure.artifact_index import combined_artifact_index


def _build_combined(tmp_path: Path) -> ReadableArtifactStore:
    engagement = tmp_path / "engagements" / "ENG" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    engagement.mkdir(parents=True)
    enterprise.mkdir()
    return combined_artifact_index(engagement, enterprise)


def test_combined_artifact_view_structurally_satisfies_readable_artifact_store(tmp_path: Path) -> None:
    combined = _build_combined(tmp_path)
    _: ReadableArtifactStore = combined  # static: no cast needed


def test_artifact_repository_accepts_a_combined_artifact_view_without_narrowing(tmp_path: Path) -> None:
    combined = _build_combined(tmp_path)
    repo = ArtifactRepository(combined)
    assert repo.read_model_version() is not None


def test_apply_file_change_and_apply_file_changes_no_longer_exist_on_artifact_repository(tmp_path: Path) -> None:
    combined = _build_combined(tmp_path)
    repo = ArtifactRepository(combined)
    assert not hasattr(repo, "apply_file_change")
    assert not hasattr(repo, "apply_file_changes")
