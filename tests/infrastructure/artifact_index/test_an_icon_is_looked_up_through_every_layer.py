"""`get_icon` reaches the index through the repository facade and the combined view, engagement first."""

from __future__ import annotations

from pathlib import Path

from src.application.artifacts.repository import ArtifactRepository
from src.infrastructure.artifact_index import combined_artifact_index
from tests.support.icon_files import icon_file, write_icon

AKS = "ICO@1790000000.aks001.azure-kubernetes-service"


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    engagement = tmp_path / "engagements" / "ENG" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    engagement.mkdir(parents=True)
    enterprise.mkdir()
    return engagement, enterprise


def test_the_combined_view_answers_with_the_engagement_s_copy_first(tmp_path: Path) -> None:
    engagement, enterprise = _roots(tmp_path)
    write_icon(enterprise, icon_file(AKS, name="Enterprise copy"))
    write_icon(engagement, icon_file(AKS, name="Engagement copy"))

    found = combined_artifact_index(engagement, enterprise).get_icon("ICO@1790000000.aks001")

    assert found is not None and found.metadata.name == "Engagement copy"


def test_the_combined_view_falls_back_to_the_enterprise(tmp_path: Path) -> None:
    engagement, enterprise = _roots(tmp_path)
    write_icon(enterprise, icon_file(AKS, name="Enterprise copy"))

    found = combined_artifact_index(engagement, enterprise).get_icon(AKS)

    assert found is not None and found.metadata.name == "Enterprise copy"


def test_the_repository_facade_delegates_to_its_store(tmp_path: Path) -> None:
    engagement, enterprise = _roots(tmp_path)
    write_icon(engagement)

    repository = ArtifactRepository(combined_artifact_index(engagement, enterprise))

    found = repository.get_icon(AKS)
    assert found is not None and found.artifact_id == AKS
    assert repository.get_icon("ICO@1790000000.nope01") is None
