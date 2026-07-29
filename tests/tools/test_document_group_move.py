"""Tests for document-collection re-homing via edit_document(group=...).

Covers the WU-C3 tool gap: edit_document previously had no way to move an
existing document into a document-collection group (artifact_edit_entity
already supported this for entities). These are the regression coverage for
that fix plus a contract test on the new group-path resolver.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write.document import create_document, edit_document


def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _adr_schema(repo: Path) -> None:
    _write(
        repo / ".arch-repo" / "documents" / "adr.json",
        '{\n  "abbreviation": "ADR",\n'
        '  "required_sections": ["Context", "Decision", "Consequences"]\n}\n',
    )


def _verifier(repo: Path) -> ArtifactVerifier:
    return ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())


def _make_adr(repo: Path, artifact_id: str) -> Path:
    result = create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _: None,
        doc_type="adr",
        title="Test ADR",
        body="## Context\n\nX\n\n## Decision\n\nY\n\n## Consequences\n\nZ\n",
        keywords=None,
        extra_frontmatter=None,
        artifact_id=artifact_id,
        version="0.1.0",
        status="draft",
        last_updated="2026-01-01",
        dry_run=False,
    )
    assert result.wrote, result.verification
    return Path(result.path)


def test_edit_document_group_relocates_file(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _adr_schema(repo)
    artifact_id = "ADR@1779000001.tgrp.standalone"
    old_path = _make_adr(repo, artifact_id)

    result = edit_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _: None,
        artifact_id=artifact_id,
        title=None,
        body=None,
        keywords=None,
        extra_frontmatter=None,
        status=None,
        version=None,
        last_updated=None,
        group="decision-records",
        dry_run=False,
    )

    assert result.wrote, result.verification
    new_path = repo / "docs" / "adr" / "decision-records" / f"{artifact_id}.md"
    assert new_path.exists()
    assert not old_path.exists()
    assert Path(result.path) == new_path


def test_edit_document_group_dry_run_previews_without_moving(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _adr_schema(repo)
    artifact_id = "ADR@1779000002.tgrp.preview"
    old_path = _make_adr(repo, artifact_id)

    result = edit_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _: None,
        artifact_id=artifact_id,
        title=None,
        body=None,
        keywords=None,
        extra_frontmatter=None,
        status=None,
        version=None,
        last_updated=None,
        group="decision-records",
        dry_run=True,
    )

    assert not result.wrote
    assert old_path.exists()
    new_path = repo / "docs" / "adr" / "decision-records" / f"{artifact_id}.md"
    assert not new_path.exists()


def test_edit_document_omitting_group_preserves_current_location(tmp_path: Path) -> None:
    """Regression: editing an unrelated field must not implicitly move the document."""
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _adr_schema(repo)
    artifact_id = "ADR@1779000003.tgrp.unrelated"
    old_path = _make_adr(repo, artifact_id)

    result = edit_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _: None,
        artifact_id=artifact_id,
        title="Renamed Title",
        body=None,
        keywords=None,
        extra_frontmatter=None,
        status=None,
        version=None,
        last_updated=None,
        dry_run=False,
    )

    assert result.wrote, result.verification
    assert old_path.exists()
    assert Path(result.path) == old_path


# ---------------------------------------------------------------------------
# artifact_edit_document(group=...) — MCP surface
# ---------------------------------------------------------------------------


def test_mcp_artifact_edit_document_group_relocates_file(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _adr_schema(repo)
    artifact_id = "ADR@1779000004.tgrp.mcp"
    old_path = _make_adr(repo, artifact_id)

    result = mcp.artifact_edit_document(
        artifact_id=artifact_id, group="decision-records", dry_run=False, repo_root=str(repo),
    )

    assert result["wrote"], result
    new_path = repo / "docs" / "adr" / "decision-records" / f"{artifact_id}.md"
    assert new_path.exists()
    assert not old_path.exists()


# ---------------------------------------------------------------------------
# _resolve_document_group_path — contract test
# ---------------------------------------------------------------------------


def test_resolve_document_group_path_returns_current_path_when_group_none(tmp_path: Path) -> None:
    from src.infrastructure.write.artifact_write.document import _resolve_document_group_path

    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _adr_schema(repo)
    current = repo / "docs" / "adr" / "ADR@1.a.x.md"
    resolved = _resolve_document_group_path(repo_root=repo, current_path=current, doc_type="adr", group=None)
    assert resolved == current


def test_resolve_document_group_path_nests_under_collection(tmp_path: Path) -> None:
    from src.infrastructure.write.artifact_write.document import _resolve_document_group_path

    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _adr_schema(repo)
    current = repo / "docs" / "adr" / "ADR@1.a.x.md"
    resolved = _resolve_document_group_path(
        repo_root=repo, current_path=current, doc_type="adr", group="decision-records"
    )
    assert resolved == repo / "docs" / "adr" / "decision-records" / "ADR@1.a.x.md"
