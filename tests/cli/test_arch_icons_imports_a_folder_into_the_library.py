"""`arch-icons import` adds a folder of icons through the same checks an upload gets, dry run first."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.cli.arch_icons import main
from tests.support.icon_files import png_of


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


def test_import_folder_through_backend(served_repo: Path, folder: Path, capsys) -> None:
    before = set(_icons(served_repo))
    assert _run(served_repo, folder) == 1
    report = capsys.readouterr().out
    assert "broken.png" in report and "Dry run" in report and set(_icons(served_repo)) == before

    assert _run(served_repo, folder, "--commit") == 1
    report = capsys.readouterr().out
    added = set(_icons(served_repo)) - before
    assert len(added) == 1 and added.pop().endswith("azure-kubernetes-service.md")
    assert "present (1)" in report and "refused (1)" in report and "readme.txt" not in report


def test_commit_requires_the_serving_backend(tmp_path: Path, folder: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("ARCH_BACKEND_STATE_DIR", str(tmp_path / "state"))
    assert _run(tmp_path, folder, "--commit") == 1
    assert "arch-backend" in capsys.readouterr().err and _icons(tmp_path) == []
