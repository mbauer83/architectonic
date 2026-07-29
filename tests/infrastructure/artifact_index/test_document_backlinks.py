from __future__ import annotations

import posixpath
from pathlib import Path

from src.application.artifact_repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index


def _write_entity(path: Path, artifact_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"artifact-id: {artifact_id}\n"
        "artifact-type: requirement\n"
        "name: Target Requirement\n"
        "version: 0.1.0\n"
        "status: active\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        "## Summary\nA target requirement.\n",
        encoding="utf-8",
    )


def _write_document(path: Path, entity_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rel = posixpath.relpath(entity_path.as_posix(), path.parent.as_posix())
    path.write_text(
        "---\n"
        "artifact-id: ADR@1.b.decision\n"
        "artifact-type: document\n"
        "doc-type: adr\n"
        "title: Decision\n"
        "status: accepted\n"
        "version: 0.1.0\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        "## Context\n"
        f"See [target]({rel}) for the architectural constraint.\n",
        encoding="utf-8",
    )


def test_read_artifact_exposes_document_backlinks(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    entity_id = "REQ@1.a.target"
    entity_path = repo / "model" / "motivation" / "requirement" / f"{entity_id}.md"
    _write_entity(entity_path, entity_id)
    _write_document(repo / "docs" / "adr" / "platform-core" / "ADR@1.b.decision.md", entity_path)

    repo_view = ArtifactRepository(shared_artifact_index(repo))
    data = repo_view.read_artifact(entity_id, mode="full")

    assert data is not None
    assert data["referenced_in_documents"] == [
        {
            "document_id": "ADR@1.b.decision",
            "title": "Decision",
            "doc_type": "adr",
            "path": str(repo / "docs" / "adr" / "platform-core" / "ADR@1.b.decision.md"),
            "section": "Context",
            "label": "target",
            "href": "../../../model/motivation/requirement/REQ@1.a.target.md",
        }
    ]
