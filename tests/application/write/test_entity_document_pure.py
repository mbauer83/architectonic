"""Tests for pure helpers in entity.py and document.py.

Covers: entity_path (group-aware), _alias_for, verification_to_entity_dict,
_dump_yaml_text, _format_document_markdown (keywords+extra_frontmatter),
_build_placeholder_body, _doc_dir (group-aware).
"""

from __future__ import annotations

from pathlib import Path

from src.domain.ontology_representation.ontology_types import EntityTypeInfo, PermittedMappingSpec
from src.domain.repository.groups import UNCATEGORIZED
from src.infrastructure.write.artifact_write.document import (
    _build_placeholder_body,
    _doc_dir,
    _dump_yaml_text,
    _format_document_markdown,
)
from src.infrastructure.write.artifact_write.entity import entity_path


def _make_info(*, hierarchy: tuple[str, ...] = ("motivation", "stakeholder")) -> EntityTypeInfo:
    return EntityTypeInfo(
        artifact_type="stakeholder",
        prefix="STK",
        hierarchy=hierarchy,
        classes=(),
        create_when="",
        never_create_when="",
        permitted_mappings=PermittedMappingSpec(),
    )


# ---------------------------------------------------------------------------
# entity_path
# ---------------------------------------------------------------------------


class TestEntityPath:
    def test_uncategorized_uses_legacy_model_root(self, tmp_path: Path) -> None:
        info = _make_info()
        path = entity_path(tmp_path, info, "STK@1.x.y")
        assert "projects" not in str(path)
        assert str(path).endswith("STK@1.x.y.md")
        assert "motivation" in str(path)
        assert "stakeholder" in str(path)

    def test_group_aware_uses_projects_layout(self, tmp_path: Path) -> None:
        info = _make_info()
        path = entity_path(tmp_path, info, "STK@1.x.y", group="my-group")
        assert "projects" in str(path)
        assert "my-group" in str(path)
        assert "motivation" in str(path)
        assert str(path).endswith("STK@1.x.y.md")

    def test_uncategorized_with_explicit_keyword(self, tmp_path: Path) -> None:
        info = _make_info()
        path = entity_path(tmp_path, info, "STK@1.x.y", group=UNCATEGORIZED)
        assert "projects" not in str(path)


# ---------------------------------------------------------------------------
# _dump_yaml_text
# ---------------------------------------------------------------------------


class TestDumpYamlText:
    def test_returns_string(self) -> None:
        result = _dump_yaml_text({"name": "foo", "version": "1.0.0"})
        assert isinstance(result, str)
        assert "name: foo" in result

    def test_strips_trailing_newline(self) -> None:
        result = _dump_yaml_text({"key": "val"})
        assert not result.endswith("\n")

    def test_handles_none_values(self) -> None:
        result = _dump_yaml_text({"a": None})
        assert "a:" in result

    def test_unicode_allowed(self) -> None:
        result = _dump_yaml_text({"title": "Äpfel"})
        assert "Äpfel" in result


# ---------------------------------------------------------------------------
# _format_document_markdown
# ---------------------------------------------------------------------------


class TestFormatDocumentMarkdown:
    def test_basic_without_keywords(self) -> None:
        md = _format_document_markdown(
            artifact_id="DOC@1.x.y",
            doc_type="adr",
            title="My Decision",
            status="draft",
            version="0.1.0",
            last_updated="2026-01-01",
            keywords=None,
            extra_frontmatter=None,
            body="## Context\n\nSome context.",
        )
        assert "DOC@1.x.y" in md
        assert "My Decision" in md
        assert "keywords" not in md

    def test_with_keywords(self) -> None:
        md = _format_document_markdown(
            artifact_id="DOC@1.x.y",
            doc_type="adr",
            title="My Decision",
            status="draft",
            version="0.1.0",
            last_updated="2026-01-01",
            keywords=["arch", "security"],
            extra_frontmatter=None,
            body="body",
        )
        assert "keywords" in md
        assert "arch" in md

    def test_with_extra_frontmatter(self) -> None:
        md = _format_document_markdown(
            artifact_id="DOC@1.x.y",
            doc_type="adr",
            title="My Decision",
            status="draft",
            version="0.1.0",
            last_updated="2026-01-01",
            keywords=None,
            extra_frontmatter={"custom-field": "custom-value"},
            body="body",
        )
        assert "custom-field" in md
        assert "custom-value" in md

    def test_extra_frontmatter_does_not_override_core_fields(self) -> None:
        md = _format_document_markdown(
            artifact_id="DOC@1.x.y",
            doc_type="adr",
            title="My Decision",
            status="draft",
            version="0.1.0",
            last_updated="2026-01-01",
            keywords=None,
            extra_frontmatter={"artifact-id": "OVERRIDE"},
            body="body",
        )
        assert md.count("DOC@1.x.y") >= 1
        assert "OVERRIDE" not in md


# ---------------------------------------------------------------------------
# _build_placeholder_body
# ---------------------------------------------------------------------------


class TestBuildPlaceholderBody:
    def test_empty_sections_returns_empty(self) -> None:
        assert _build_placeholder_body([]) == ""

    def test_one_section(self) -> None:
        body = _build_placeholder_body(["Context"])
        assert "## Context" in body
        assert "Add content here" in body

    def test_multiple_sections(self) -> None:
        body = _build_placeholder_body(["Context", "Decision", "Consequences"])
        assert "## Context" in body
        assert "## Decision" in body
        assert "## Consequences" in body


# ---------------------------------------------------------------------------
# _doc_dir
# ---------------------------------------------------------------------------


class TestDocDir:
    def test_uncategorized_returns_base(self, tmp_path: Path) -> None:
        d = _doc_dir(tmp_path, "adr")
        assert "projects" not in str(d)
        assert "adr" in str(d)

    def test_group_aware_appends_group(self, tmp_path: Path) -> None:
        d = _doc_dir(tmp_path, "adr", group="my-collection")
        assert "my-collection" in str(d)
        assert "adr" in str(d)
