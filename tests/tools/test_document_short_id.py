"""edit_document/delete_document accept the short (rename-stable) artifact id form.

Regression coverage: both previously globbed for the exact filename `{artifact_id}.md`,
so a short id (no trailing `.slug`) always raised "not found" even though the document
existed under its full-id filename.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.document import create_document, delete_document, edit_document


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _schema(repo: Path) -> None:
    _write(
        repo / ".arch-repo" / "documents" / "adr.json",
        """\
{
  "abbreviation": "ADR",
  "name": "Architecture Decision Record",
  "required_sections": ["Context", "Decision", "Consequences"]
}
""",
    )


def _verifier(repo: Path) -> ArtifactVerifier:
    return ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())


def _create(repo: Path, artifact_id: str) -> Path:
    result = create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        doc_type="adr",
        title="Short Id Regression",
        body="## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nc\n",
        keywords=None,
        extra_frontmatter=None,
        artifact_id=artifact_id,
        version="0.1.0",
        status="draft",
        last_updated="2026-04-22",
        dry_run=False,
    )
    assert result.wrote, result
    return result.path


def test_edit_document_resolves_short_form_id(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo)
    full_id = "ADR@1000000010.ShortEd.short-id-edit"
    path = _create(repo, full_id)
    short_id = "ADR@1000000010.ShortEd"

    result = edit_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        artifact_id=short_id,
        title="Renamed via Short Id",
        body=None,
        keywords=None,
        extra_frontmatter=None,
        status=None,
        version=None,
        last_updated="2026-04-23",
        dry_run=False,
    )

    assert result.wrote, result
    assert result.path == path
    assert "Renamed via Short Id" in path.read_text(encoding="utf-8")


def test_delete_document_resolves_short_form_id(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo)
    full_id = "ADR@1000000011.ShortDl.short-id-delete"
    path = _create(repo, full_id)
    short_id = "ADR@1000000011.ShortDl"

    result = delete_document(
        repo_root=repo,
        clear_repo_caches=lambda _path: None,
        artifact_id=short_id,
        dry_run=False,
    )

    assert result.wrote, result
    assert not path.exists()


def test_edit_document_ambiguous_short_id_raises_not_found(tmp_path: Path) -> None:
    """Two documents sharing one short id (a genuine rename/shadow collision) must
    fail closed rather than silently editing whichever the scan happened to see first."""
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo)
    _create(repo, "ADR@1000000012.Ambig1.first-slug")
    docs_root = repo / "docs" / "adr"
    duplicate = docs_root / "ADR@1000000012.Ambig1.second-slug.md"
    duplicate.write_text(
        (docs_root / "ADR@1000000012.Ambig1.first-slug.md").read_text(encoding="utf-8").replace(
            "first-slug", "second-slug"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not found"):
        edit_document(
            repo_root=repo,
            verifier=_verifier(repo),
            clear_repo_caches=lambda _path: None,
            artifact_id="ADR@1000000012.Ambig1",
            title="Should Not Apply",
            body=None,
            keywords=None,
            extra_frontmatter=None,
            status=None,
            version=None,
            last_updated="2026-04-23",
            dry_run=False,
        )
