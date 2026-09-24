"""An incremental update and a full scan agree on every file of a repository.

Before the layout had one reading of which artifact a path holds, the incremental index parsed any
`.md` it did not recognise as an entity, wherever it sat — a README, a note in a project directory,
a file under a catalog directory the scan never walks — while a full scan indexed none of them. The
two views disagreed until the next refresh.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.artifact_index.service import ArtifactIndex

_FRONTMATTER = (
    "---\nartifact-id: {aid}\nartifact-type: {atype}\nname: {name}\nversion: 0.1.0\nstatus: draft\n"
    "last-updated: '2026-01-01'\n---\n\n## {name}\n"
)


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    _write(root, ".arch-repo/documents/adr.json", '{"abbreviation": "ADR", "required_sections": []}')
    entity = _FRONTMATTER.format(aid="REQ@1.aaaa.probe", atype="requirement", name="Probe")
    _write(root, "projects/core/model/motivation/requirement/REQ@1.aaaa.probe.md", entity)
    _write(root, "model/motivation/requirement/REQ@2.bbbb.legacy.md",
           _FRONTMATTER.format(aid="REQ@2.bbbb.legacy", atype="requirement", name="Legacy"))
    looks_like_an_entity = _FRONTMATTER.format(aid="REQ@3.cccc.stray", atype="requirement", name="Stray")
    for stray in (
        "README.md",
        "projects/core/NOTES.md",
        "diagram-catalog/icons/REQ@3.cccc.stray.md",
        "diagram-catalog/rendered/core/REQ@3.cccc.stray.md",
    ):
        _write(root, stray, looks_like_an_entity)
    return root


def _indexed(index: ArtifactIndex) -> dict[str, set[str]]:
    return {
        "entities": {e.artifact_id for e in index.list_entities()},
        "documents": {d.artifact_id for d in index.list_documents()},
        "diagrams": {d.artifact_id for d in index.list_diagrams()},
    }


def test_updating_each_file_leaves_what_a_full_scan_indexed(repo: Path) -> None:
    index = ArtifactIndex(repo)
    try:
        index.refresh()
        scanned = _indexed(index)
        for path in sorted(p for p in repo.rglob("*") if p.is_file()):
            index.apply_file_changes([path])
            assert _indexed(index) == scanned, path.relative_to(repo)
    finally:
        index.close()

    assert {"REQ@1.aaaa.probe", "REQ@2.bbbb.legacy"} <= scanned["entities"]
    assert "REQ@3.cccc.stray" not in scanned["entities"]
