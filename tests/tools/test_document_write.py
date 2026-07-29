from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.document import create_document, edit_document


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _schema(repo: Path, *, subdirectory: str | None = None) -> None:
    subdirectory_field = f',\n  "subdirectory": "{subdirectory}"' if subdirectory is not None else ""
    _write(
        repo / ".arch-repo" / "documents" / "adr.json",
        """\
{
  "abbreviation": "ADR",
  "name": "Architecture Decision Record"%s,
  "required_sections": ["Context", "Decision", "Consequences"]
}
"""
        % subdirectory_field,
    )


def _verifier(repo: Path) -> ArtifactVerifier:
    return ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())


def test_create_document_uses_schema_subdirectory(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo, subdirectory="decisions/adr")

    result = create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        doc_type="adr",
        title="Adopt Structured Document Paths",
        body=None,
        keywords=None,
        extra_frontmatter=None,
        artifact_id="ADR@1000000000.AbcDef.structured-paths",
        version="0.1.0",
        status="draft",
        last_updated="2026-04-22",
        dry_run=False,
    )

    assert result.path == repo / "docs" / "decisions" / "adr" / "ADR@1000000000.AbcDef.structured-paths.md"
    assert result.path.exists()


def test_create_document_defaults_subdirectory_to_doc_type(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo)

    result = create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        doc_type="adr",
        title="Fallback Directory",
        body=None,
        keywords=None,
        extra_frontmatter=None,
        artifact_id="ADR@1000000001.AbcDef.fallback-directory",
        version="0.1.0",
        status="draft",
        last_updated="2026-04-22",
        dry_run=False,
    )

    assert result.path == repo / "docs" / "adr" / "ADR@1000000001.AbcDef.fallback-directory.md"
    assert result.path.exists()


def test_create_document_refuses_missing_required_section(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo)

    result = create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        doc_type="adr",
        title="Missing Sections",
        body="## Context\n\nOnly context.\n",
        keywords=None,
        extra_frontmatter=None,
        artifact_id="ADR@1000000002.AbcDef.missing-sections",
        version="0.1.0",
        status="draft",
        last_updated="2026-04-22",
        dry_run=False,
    )

    assert result.wrote is False
    assert any(issue["code"] == "E154" for issue in result.verification["issues"])
    assert not result.path.exists()


def test_create_document_refuses_broken_internal_reference(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo)

    result = create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        doc_type="adr",
        title="Broken Reference",
        body=(
            "## Context\n\nSee [Missing](../spec/NOPE.md).\n\n"
            "## Decision\n\nDecision.\n\n"
            "## Consequences\n\nConsequences.\n"
        ),
        keywords=None,
        extra_frontmatter=None,
        artifact_id="ADR@1000000003.AbcDef.broken-reference",
        version="0.1.0",
        status="draft",
        last_updated="2026-04-22",
        dry_run=False,
    )

    assert result.wrote is False
    assert any(issue["code"] == "W155" for issue in result.verification["issues"])
    assert not result.path.exists()


def test_create_document_resolves_link_into_grouped_entity(tmp_path: Path) -> None:
    """Regression: dry-run/verify only symlinked ARCH_REPO+MODEL into the verification
    sandbox, so a link into an entity re-homed under projects/<group>/model/... always
    read as W155-broken even though it resolves fine in the live repo."""
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo)
    grouped_entity = repo / "projects" / "my-group" / "model" / "motivation" / "requirement" / "REQ@1.a.probe.md"
    _write(
        grouped_entity,
        "---\nartifact-id: REQ@1.a.probe\nartifact-type: requirement\nname: Probe\n"
        "version: 0.1.0\nstatus: draft\nlast-updated: '2026-01-01'\n---\n\n## Probe\n",
    )

    result = create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        doc_type="adr",
        title="Links Into Grouped Entity",
        body=(
            "## Context\n\nSee [Probe](../../projects/my-group/model/motivation/requirement/REQ@1.a.probe.md).\n\n"
            "## Decision\n\nDecision.\n\n"
            "## Consequences\n\nConsequences.\n"
        ),
        keywords=None,
        extra_frontmatter=None,
        artifact_id="ADR@1000000004.AbcDef.grouped-link",
        version="0.1.0",
        status="draft",
        last_updated="2026-04-22",
        dry_run=False,
    )

    assert result.wrote is True, result.verification


def test_create_grouped_document_resolves_relative_entity_link(tmp_path: Path) -> None:
    """Regression: the verification sandbox placed the document at docs/<subdir>/<file>,
    dropping the group segment, so relative links written for the real depth
    (docs/<subdir>/<group>/<file>) resolved one level short and reported W155 —
    blocking the write even though the link is valid at the real location."""
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo)
    grouped_entity = repo / "projects" / "my-group" / "model" / "motivation" / "requirement" / "REQ@1.a.probe.md"
    _write(
        grouped_entity,
        "---\nartifact-id: REQ@1.a.probe\nartifact-type: requirement\nname: Probe\n"
        "version: 0.1.0\nstatus: draft\nlast-updated: '2026-01-01'\n---\n\n## Probe\n",
    )

    result = create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        doc_type="adr",
        title="Grouped Document With Entity Link",
        body=(
            "## Context\n\nContext.\n\n"
            "## Decision\n\nSee "
            "[Probe](../../../projects/my-group/model/motivation/requirement/REQ@1.a.probe.md).\n\n"
            "## Consequences\n\nConsequences.\n"
        ),
        keywords=None,
        extra_frontmatter=None,
        artifact_id="ADR@1000000005.AbcDef.grouped-doc-link",
        version="0.1.0",
        status="draft",
        last_updated="2026-04-22",
        dry_run=False,
        group="platform-core",
    )

    assert result.wrote is True, result.verification
    assert result.path.parent.name == "platform-core"
    assert result.path.exists()


def test_edit_document_refuses_invalid_update(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    _schema(repo)

    created = create_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        doc_type="adr",
        title="Editable ADR",
        body=None,
        keywords=None,
        extra_frontmatter=None,
        artifact_id="ADR@1000000004.AbcDef.editable-adr",
        version="0.1.0",
        status="draft",
        last_updated="2026-04-22",
        dry_run=False,
    )
    assert created.wrote is True

    original = created.path.read_text(encoding="utf-8")
    result = edit_document(
        repo_root=repo,
        verifier=_verifier(repo),
        clear_repo_caches=lambda _path: None,
        artifact_id="ADR@1000000004.AbcDef.editable-adr",
        title=None,
        body="## Context\n\nInvalid update.\n",
        keywords=None,
        extra_frontmatter=None,
        status=None,
        version=None,
        last_updated="2026-04-23",
        dry_run=False,
    )

    assert result.wrote is False
    assert any(issue["code"] == "E154" for issue in result.verification["issues"])
    assert created.path.read_text(encoding="utf-8") == original
