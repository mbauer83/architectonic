"""`arch-icons import` adds a folder of icons through the same checks an upload gets, dry run first."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.cli.arch_icons import main
from src.infrastructure.rendering.generate_static_includes import generate_static_includes
from tests.support.icon_files import png_of


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    for directory in ("model", "docs", "diagram-catalog/diagrams"):
        (root / directory).mkdir(parents=True)
    generate_static_includes(root)
    return root


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    pack = tmp_path / "azure-pack"
    pack.mkdir()
    (pack / "Azure_Kubernetes-Service.png").write_bytes(png_of((0, 120, 212, 255)))
    (pack / "same-picture-again.png").write_bytes(png_of((0, 120, 212, 255)))
    (pack / "broken.png").write_bytes(b"not an image")
    (pack / "readme.txt").write_text("ignored", encoding="utf-8")
    return pack


def _icons(repo: Path) -> list[str]:
    library = repo / "diagram-catalog" / "icons"
    return sorted(p.name for p in library.glob("*.md")) if library.exists() else []


def _run(repo: Path, folder: Path, *extra: str) -> int:
    return main(["import", str(folder), "--attribution", "Test pack", "--tag", "azure",
                 "--for", "technology-node", "--repo", str(repo), *extra])


def test_a_dry_run_reports_and_writes_nothing(repo: Path, folder: Path, capsys) -> None:
    code = _run(repo, folder)

    report = capsys.readouterr().out
    assert code == 1 and "broken.png" in report and "Dry run" in report and _icons(repo) == []


def test_a_commit_adds_each_new_picture_once_and_names_the_rest(repo: Path, folder: Path, capsys) -> None:
    _run(repo, folder, "--commit")

    report = capsys.readouterr().out
    assert len(_icons(repo)) == 1 and _icons(repo)[0].endswith("azure-kubernetes-service.md")
    assert "present (1)" in report and "refused (1)" in report and "readme.txt" not in report
