"""Tests for document-spec section_templates: per-section body injection and spec validation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.document import (
    _build_placeholder_body,
    _validate_section_templates,
    create_document,
)


@lru_cache(maxsize=1)
def _catalogs():
    from src.infrastructure.app_bootstrap import build_module_registry, build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(build_module_registry())


@lru_cache(maxsize=1)
def _all_entity_types() -> dict:
    from src.infrastructure.app_bootstrap import build_module_registry  # noqa: PLC0415

    return {str(k): v for k, v in build_module_registry().all_entity_types().items()}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _adr_schema(repo: Path, section_templates: str = "") -> None:
    templates_field = f',\n  "section_templates": {section_templates}' if section_templates else ""
    base = (
        '{\n  "abbreviation": "ADR",\n'
        '  "required_sections": ["Context", "Decision", "Consequences"]'
    )
    _write(repo / ".arch-repo" / "documents" / "adr.json", f"{base}{templates_field}\n}}\n")


def _adr_schema_sections(repo: Path, sections: str) -> None:
    _write(
        repo / ".arch-repo" / "documents" / "adr.json",
        f"""\
{{
  "abbreviation": "ADR",
  "sections": {sections}
}}
""",
    )


def _verifier(repo: Path) -> ArtifactVerifier:
    return ArtifactVerifier(ArtifactRegistry(shared_artifact_index(repo)), catalogs=_catalogs())


# ── pure unit: _build_placeholder_body ─────────────────────────────────────

class TestBuildPlaceholderBody:
    def test_no_templates_uses_comment_placeholder(self) -> None:
        result = _build_placeholder_body(["Context", "Decision"])
        assert "## Context" in result
        assert "<!-- Add content here -->" in result

    def test_section_with_template_uses_template_body(self) -> None:
        templates = {"Context": "Describe the problem here.\n", "Decision": "Describe the decision.\n"}
        result = _build_placeholder_body(["Context", "Decision"], templates)
        assert "## Context\n\nDescribe the problem here." in result
        assert "## Decision\n\nDescribe the decision." in result
        assert "<!-- Add content here -->" not in result

    def test_partial_template_mixes_template_and_placeholder(self) -> None:
        templates = {"Decision": "Describe the decision.\n"}
        result = _build_placeholder_body(["Context", "Decision", "Consequences"], templates)
        assert "## Context\n\n<!-- Add content here -->" in result
        assert "## Decision\n\nDescribe the decision." in result
        assert "## Consequences\n\n<!-- Add content here -->" in result

    def test_empty_templates_dict_uses_comment_placeholder(self) -> None:
        result = _build_placeholder_body(["Context"], {})
        assert "<!-- Add content here -->" in result

    def test_template_body_is_stripped_trailing_whitespace(self) -> None:
        templates = {"Context": "Some content.   \n   "}
        result = _build_placeholder_body(["Context"], templates)
        assert "Some content." in result
        assert result.count("Some content.") == 1

    def test_canonical_section_entries_include_expected_link_hints(self) -> None:
        result = _build_placeholder_body(
            [
                {
                    "name": "Context",
                    "template": "Describe the context.\n",
                    "required_entity_type_connections": ["requirement"],
                    "suggested_entity_type_connections": ["capability"],
                }
            ]
        )
        assert "## Context" in result
        assert "<!-- Expected entity links for this section: required: requirement; suggested: capability -->" in result
        assert "Describe the context." in result


# ── pure unit: _validate_section_templates ─────────────────────────────────

class TestValidateSectionTemplates:
    def test_valid_templates_pass(self) -> None:
        _validate_section_templates(
            {"Context": "foo", "Decision": "bar"},
            ["Context", "Decision", "Consequences"],
            "adr",
        )

    def test_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="must be an object"):
            _validate_section_templates(["Context"], ["Context"], "adr")

    def test_key_not_in_required_sections_raises(self) -> None:
        with pytest.raises(ValueError, match="not in required_sections"):
            _validate_section_templates(
                {"UnknownSection": "foo"},
                ["Context", "Decision"],
                "adr",
            )

    def test_non_string_value_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a string"):
            _validate_section_templates({"Context": 42}, ["Context"], "adr")  # type: ignore[arg-type]

    def test_empty_dict_is_valid(self) -> None:
        _validate_section_templates({}, ["Context", "Decision"], "adr")


# ── integration: create_document uses section_templates ────────────────────

class TestCreateDocumentSectionTemplates:
    def test_creates_body_from_section_templates_when_body_omitted(self, tmp_path: Path) -> None:
        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        _adr_schema(
            repo,
            section_templates=(
                '{"Context": "Describe the context.\\n",'
                ' "Decision": "State the decision.\\n",'
                ' "Consequences": "List the consequences.\\n"}'
            ),
        )
        result = create_document(
            repo_root=repo,
            verifier=_verifier(repo),
            clear_repo_caches=lambda _: None,
            doc_type="adr",
            title="Test ADR with Templates",
            body=None,
            keywords=None,
            extra_frontmatter=None,
            artifact_id="ADR@1000000001.Test.test-adr",
            version="0.1.0",
            status="draft",
            last_updated="2026-06-19",
            dry_run=False,
        )
        assert result.wrote
        path = result.path
        assert path is not None
        content = Path(path).read_text(encoding="utf-8")
        assert "## Context\n\nDescribe the context." in content
        assert "## Decision\n\nState the decision." in content
        assert "<!-- Add content here -->" not in content

    def test_explicit_body_overrides_section_templates(self, tmp_path: Path) -> None:
        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        _adr_schema(
            repo,
            section_templates='{"Context": "Template context.\\n"}',
        )
        explicit_body = (
            "## Context\n\nCustom body.\n\n"
            "## Decision\n\nCustom decision.\n\n"
            "## Consequences\n\nCustom consequences.\n"
        )
        result = create_document(
            repo_root=repo,
            verifier=_verifier(repo),
            clear_repo_caches=lambda _: None,
            doc_type="adr",
            title="Test Explicit Body",
            body=explicit_body,
            keywords=None,
            extra_frontmatter=None,
            artifact_id="ADR@1000000002.Test.explicit-body",
            version="0.1.0",
            status="draft",
            last_updated="2026-06-19",
            dry_run=False,
        )
        assert result.wrote
        content = Path(result.path).read_text(encoding="utf-8")
        assert "Custom body." in content
        assert "Template context." not in content

    def test_malformed_section_templates_in_spec_raises(self, tmp_path: Path) -> None:
        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        _adr_schema(repo, section_templates='{"UnknownSection": "foo"}')
        with pytest.raises(ValueError, match="not in required_sections"):
            create_document(
                repo_root=repo,
                verifier=_verifier(repo),
                clear_repo_caches=lambda _: None,
                doc_type="adr",
                title="Bad Spec ADR",
                body=None,
                keywords=None,
                extra_frontmatter=None,
                artifact_id="ADR@1000000003.Test.bad-spec",
                version="0.1.0",
                status="draft",
                last_updated="2026-06-19",
                dry_run=False,
            )

    def test_section_without_template_falls_back_to_comment(self, tmp_path: Path) -> None:
        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        _adr_schema(
            repo,
            section_templates='{"Context": "Describe the context.\\n"}',
        )
        result = create_document(
            repo_root=repo,
            verifier=_verifier(repo),
            clear_repo_caches=lambda _: None,
            doc_type="adr",
            title="Partial Templates ADR",
            body=None,
            keywords=None,
            extra_frontmatter=None,
            artifact_id="ADR@1000000004.Test.partial-templates",
            version="0.1.0",
            status="draft",
            last_updated="2026-06-19",
            dry_run=False,
        )
        assert result.wrote
        content = Path(result.path).read_text(encoding="utf-8")
        assert "## Context\n\nDescribe the context." in content
        assert "## Decision\n\n<!-- Add content here -->" in content
        assert "## Consequences\n\n<!-- Add content here -->" in content

    def test_creates_placeholder_body_from_canonical_sections_with_hints(self, tmp_path: Path) -> None:
        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        _adr_schema_sections(
            repo,
            (
                '[{"name": "Context", "template": "Describe the context.\\n", '
                '"required_entity_type_connections": ["requirement"]}, '
                '{"name": "Decision", "suggested_entity_type_connections": ["capability"]}]'
            ),
        )
        result = create_document(
            repo_root=repo,
            verifier=_verifier(repo),
            clear_repo_caches=lambda _: None,
            doc_type="adr",
            title="Canonical Sections ADR",
            body=None,
            keywords=None,
            extra_frontmatter=None,
            artifact_id="ADR@1000000005.Test.canonical-sections",
            version="0.1.0",
            status="draft",
            last_updated="2026-06-19",
            dry_run=True,
        )
        assert result.content is not None
        assert "## Context" in result.content
        assert "<!-- Expected entity links for this section: required: requirement -->" in result.content
        assert "Describe the context." in result.content
        assert "## Decision" in result.content
        assert "<!-- Expected entity links for this section: suggested: capability -->" in result.content


# ── end-to-end: real `standard` seed schema, create → placeholder → verify ──


class TestStandardDocTypeSectionLifecycle:
    """Dogfoods the seeded `standard` doc-type exemplar (per-section rules, not document-level)."""

    def _seed_standard_schema(self, repo: Path) -> None:
        from src.domain.repository.repo_default_schemata import BASE_DOCUMENT_SCHEMAS

        _write(
            repo / ".arch-repo" / "documents" / "standard.json",
            json.dumps(BASE_DOCUMENT_SCHEMAS["standard"]),
        )

    def test_placeholder_places_link_hints_in_their_own_sections(self, tmp_path: Path) -> None:
        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        self._seed_standard_schema(repo)
        result = create_document(
            repo_root=repo,
            verifier=_verifier(repo),
            clear_repo_caches=lambda _: None,
            doc_type="standard",
            title="Test Standard",
            body=None,
            keywords=None,
            extra_frontmatter={"applies_to": ["testing"]},
            artifact_id="STD@1000000010.Test.test-standard",
            version="0.1.0",
            status="draft",
            last_updated="2026-06-19",
            dry_run=True,
        )
        assert result.content is not None
        assert "## Specification" in result.content
        assert "<!-- Expected entity links for this section: required: requirement -->" in result.content
        assert "## Motivation" in result.content
        assert "<!-- Expected entity links for this section: suggested: principle, goal -->" in result.content
        # The document-level rule moved into "Specification"; "Scope"/"Summary" carry no hint.
        assert "## Scope\n\nState what this standard applies to" in result.content

    def test_verifier_reports_e156_until_requirement_linked_in_specification(self, tmp_path: Path) -> None:
        repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
        self._seed_standard_schema(repo)
        info = _all_entity_types()["requirement"]
        req_id = "REQ@1000000011.Test.my-req"
        req_path = repo / "model" / Path(*info.hierarchy) / f"{req_id}.md"
        _write(
            req_path,
            "---\n"
            f"artifact-id: {req_id}\n"
            "artifact-type: requirement\n"
            'name: "My Requirement"\n'
            "version: 0.1.0\n"
            "status: draft\n"
            "last-updated: '2026-06-19'\n"
            "---\n\n"
            "<!-- §content -->\n\n"
            "## My Requirement\n\n"
            "<!-- §display -->\n",
        )

        # The placeholder body carries no entity links yet, so writing it for real would be
        # blocked by the same E156 check (write-time verification requires no issues) — preview
        # it instead, then place the still-unlinked placeholder on disk as an author would before
        # filling it in, and verify it standalone.
        result = create_document(
            repo_root=repo,
            verifier=_verifier(repo),
            clear_repo_caches=lambda _: None,
            doc_type="standard",
            title="Test Standard",
            body=None,
            keywords=None,
            extra_frontmatter={"applies_to": ["testing"]},
            artifact_id="STD@1000000012.Test.test-standard2",
            version="0.1.0",
            status="draft",
            last_updated="2026-06-19",
            dry_run=True,
        )
        assert result.content is not None
        doc_path = Path(result.path)
        _write(doc_path, result.content)

        before = _verifier(repo).verify_document_file(doc_path)
        assert any(
            i.code == "E156" and "Specification" in i.message for i in before.issues
        ), [i.message for i in before.issues]

        rel = Path("../../model") / Path(*info.hierarchy) / f"{req_id}.md"
        content = doc_path.read_text(encoding="utf-8")
        updated = content.replace(
            "## Specification\n\n",
            f"## Specification\n\n[My Requirement]({rel.as_posix()})\n\n",
            1,
        )
        doc_path.write_text(updated, encoding="utf-8")

        after = _verifier(repo).verify_document_file(doc_path)
        assert not any(i.code == "E156" for i in after.issues), [i.message for i in after.issues]
