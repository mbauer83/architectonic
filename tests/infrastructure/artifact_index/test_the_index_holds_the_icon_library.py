"""The index holds every readable icon file of a repository, and follows each change to one."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.artifact_index.service import ArtifactIndex
from tests.support.icon_files import icon_file, png_of, write_icon

AKS = "ICO@1790000000.aks001.azure-kubernetes-service"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    return root


@pytest.fixture
def index(repo: Path):
    built = ArtifactIndex(repo)
    yield built
    built.close()


def _ids(index: ArtifactIndex) -> list[str]:
    return [icon.artifact_id for icon in index.list_icons()]


def test_a_scan_finds_the_icon_and_a_short_id_reaches_it(repo: Path, index: ArtifactIndex) -> None:
    path = write_icon(repo)
    index.refresh()

    assert _ids(index) == [AKS]
    found = index.get_icon("ICO@1790000000.aks001")
    assert found is not None and found.path == path and found.metadata.name == "Azure Kubernetes Service"
    assert index.find_file_by_id(AKS) == path


def test_an_unreadable_icon_file_is_not_indexed(repo: Path, index: ArtifactIndex) -> None:
    (repo / "diagram-catalog" / "icons").mkdir(parents=True)
    (repo / "diagram-catalog" / "icons" / f"{AKS}.md").write_text("---\nartifact-type: icon\n---\n", encoding="utf-8")
    index.refresh()

    assert _ids(index) == []


def test_each_change_to_an_icon_file_leaves_what_a_full_scan_would(repo: Path, index: ArtifactIndex) -> None:
    index.refresh()
    path = write_icon(repo)
    steps = [
        lambda: None,
        lambda: write_icon(repo, icon_file(name="AKS (renamed)", png=png_of((255, 0, 0, 255)))),
        path.unlink,
    ]
    for step in steps:
        step()
        index.apply_file_changes([path])
        incremental = [(i.artifact_id, i.metadata.name) for i in index.list_icons()]
        index.refresh()
        assert incremental == [(i.artifact_id, i.metadata.name) for i in index.list_icons()]

    assert _ids(index) == []
