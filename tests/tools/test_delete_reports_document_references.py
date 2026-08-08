"""Deleting an entity says which documents will be left pointing at nothing.

A document sits beside the model and references it one-way — a markdown link into an entity file —
so nothing in the model records the dependency. A rename rewrites those links; a deletion cannot,
and the verifier resolves a document's links by skipping the ones that hit no file. Without this
warning the sequence is silent from end to end: an ADR goes on citing an element that no longer
exists, and the first reader to follow the link finds out.

Deliberately a warning rather than a blocker. The model is not made inconsistent by a dangling link
in prose, and a decision record legitimately mentions things that are later removed — blocking would
make deleting anything an ADR ever named impossible. Deleting a whole model project *does* block,
because the blast radius is different.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.admin_tools import artifact_admin_reindex

CITED = "APP@1786120001.Aa1Bb2.cited-component"
UNCITED = "APP@1786120001.Cc3Dd4.uncited-component"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    schema_dir = root / ".arch-repo" / "documents"
    schema_dir.mkdir(parents=True)
    (schema_dir / "adr.json").write_text(json.dumps({
        "abbreviation": "ADR",
        "name": "Architecture Decision Record",
        "subdirectory": "adr",
        "frontmatter_schema": {"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}},
        "sections": [{"name": "Context"}],
    }), encoding="utf-8")
    for artifact_id, name in ((CITED, "Cited Component"), (UNCITED, "Uncited Component")):
        assert mcp.artifact_create_entity(
            artifact_type="application-component", name=name, artifact_id=artifact_id,
            dry_run=False, repo_root=str(root),
        )["wrote"]
    return root


def _entity_path(repo: Path, artifact_id: str) -> Path:
    hit = next(repo.rglob(f"{artifact_id}.md"))
    return hit


def _document_citing(repo: Path, artifact_id: str) -> str:
    """An ADR linking to the entity the way the real ones do — a relative path with the slug."""
    target = _entity_path(repo, artifact_id)
    created = mcp.artifact_create_document(
        doc_type="adr", title="A Decision That Cites It", dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created
    doc_path = Path(created["path"])
    relative = Path(os.path.relpath(target, doc_path.parent))
    doc_path.write_text(
        doc_path.read_text(encoding="utf-8")
        + f"\n\nSee [Cited Component]({relative.as_posix()}) for the component this decides about.\n",
        encoding="utf-8",
    )
    return str(created["artifact_id"])


def _warnings(result: object) -> list[str]:
    return list((result or {}).get("warnings", []))  # type: ignore[union-attr]


class TestWhatDeletionSaysAboutDocuments:
    def test_a_citing_document_is_named_in_the_warnings(self, repo: Path) -> None:
        document_id = _document_citing(repo, CITED)
        artifact_admin_reindex(repo_root=str(repo))

        result = mcp.artifact_delete_entity(artifact_id=CITED, dry_run=True, repo_root=str(repo))

        joined = " ".join(_warnings(result))
        assert document_id in joined, _warnings(result)
        assert "no longer exists" in joined

    def test_the_deletion_still_proceeds(self, repo: Path) -> None:
        """A warning, not a blocker: prose citing a removed element is not model inconsistency."""
        _document_citing(repo, CITED)
        artifact_admin_reindex(repo_root=str(repo))

        result = mcp.artifact_delete_entity(artifact_id=CITED, dry_run=False, repo_root=str(repo))

        assert result["wrote"], result
        assert not list(repo.rglob(f"{CITED}.md"))

    def test_an_uncited_entity_warns_about_no_documents(self, repo: Path) -> None:
        _document_citing(repo, CITED)
        artifact_admin_reindex(repo_root=str(repo))

        result = mcp.artifact_delete_entity(artifact_id=UNCITED, dry_run=True, repo_root=str(repo))

        assert all("document" not in w for w in _warnings(result)), _warnings(result)
