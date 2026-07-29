"""Tests for pure functions in artifact_write/_matrix_content.py.

Covers: _infer_entity_ids_from_matrix, _read_frontmatter,
_display_name_from_entity_file, _build_diagram_id_to_relpath,
_linkify_known_tokens_in_matrix_rows, _linkify_matrix_ids.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactRegistry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write._matrix_content import (
    _build_diagram_id_to_relpath,
    _display_name_from_entity_file,
    _infer_entity_ids_from_matrix,
    _linkify_known_tokens_in_matrix_rows,
    _linkify_matrix_ids,
    _read_frontmatter,
)

# ---------------------------------------------------------------------------
# _infer_entity_ids_from_matrix
# ---------------------------------------------------------------------------


class TestInferEntityIdsFromMatrix:
    def test_extracts_entity_ids_from_table(self) -> None:
        md = "| ENT@1.foo.bar | ENT@2.baz.qux |\n|---|\n| value |"
        ids = _infer_entity_ids_from_matrix(md)
        assert "ENT@1.foo.bar" in ids
        assert "ENT@2.baz.qux" in ids

    def test_deduplicates_ids(self) -> None:
        md = "| ENT@1.foo.bar | ENT@1.foo.bar |\n"
        ids = _infer_entity_ids_from_matrix(md)
        assert ids.count("ENT@1.foo.bar") == 1

    def test_returns_sorted(self) -> None:
        md = "| ENT@2.b.b | ENT@1.a.a |"
        ids = _infer_entity_ids_from_matrix(md)
        assert ids == sorted(ids)

    def test_empty_markdown_returns_empty(self) -> None:
        assert _infer_entity_ids_from_matrix("") == []

    def test_no_entity_ids_returns_empty(self) -> None:
        assert _infer_entity_ids_from_matrix("| foo | bar |\n") == []


# ---------------------------------------------------------------------------
# _read_frontmatter
# ---------------------------------------------------------------------------


class TestReadFrontmatter:
    def test_reads_valid_frontmatter(self, tmp_path: Path) -> None:
        f = tmp_path / "entity.md"
        f.write_text("---\nname: My Entity\nartifact-id: ENT@1.x.y\n---\nbody\n")
        fm = _read_frontmatter(f)
        assert fm["name"] == "My Entity"
        assert fm["artifact-id"] == "ENT@1.x.y"

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        fm = _read_frontmatter(tmp_path / "nonexistent.md")
        assert fm == {}

    def test_returns_empty_when_no_frontmatter_delimiter(self, tmp_path: Path) -> None:
        f = tmp_path / "plain.md"
        f.write_text("just text, no frontmatter\n")
        assert _read_frontmatter(f) == {}

    def test_returns_empty_when_frontmatter_not_closed(self, tmp_path: Path) -> None:
        f = tmp_path / "unclosed.md"
        f.write_text("---\nname: Foo\n")
        assert _read_frontmatter(f) == {}

    def test_returns_empty_for_invalid_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.md"
        f.write_text("---\n{invalid: [yaml\n---\nbody\n")
        assert _read_frontmatter(f) == {}

    def test_returns_empty_when_yaml_not_dict(self, tmp_path: Path) -> None:
        f = tmp_path / "scalar.md"
        f.write_text("---\n- list item\n---\nbody\n")
        assert _read_frontmatter(f) == {}


# ---------------------------------------------------------------------------
# _display_name_from_entity_file
# ---------------------------------------------------------------------------


class TestDisplayNameFromEntityFile:
    def test_returns_name_from_frontmatter(self, tmp_path: Path) -> None:
        f = tmp_path / "ent.md"
        f.write_text("---\nname: My Component\n---\nbody\n")
        result = _display_name_from_entity_file(f, "ENT@1.x.y")
        assert result == "My Component"

    def test_falls_back_to_artifact_id_when_no_name(self, tmp_path: Path) -> None:
        f = tmp_path / "ent.md"
        f.write_text("---\n---\nbody\n")
        result = _display_name_from_entity_file(f, "ENT@1.x.y")
        assert result == "ENT@1.x.y"

    def test_falls_back_when_name_is_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "ent.md"
        f.write_text("---\nname: ''\n---\nbody\n")
        result = _display_name_from_entity_file(f, "ENT@1.x.y")
        assert result == "ENT@1.x.y"

    def test_falls_back_when_file_missing(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.md"
        result = _display_name_from_entity_file(f, "ENT@9.x.y")
        assert result == "ENT@9.x.y"


# ---------------------------------------------------------------------------
# _build_diagram_id_to_relpath
# ---------------------------------------------------------------------------


class TestBuildDiagramIdToRelpath:
    def test_finds_puml_files(self, tmp_path: Path) -> None:
        diagrams = tmp_path / "diagrams"
        diagrams.mkdir()
        (diagrams / "DIAG@1.abc.puml").write_text("@startuml\n@enduml\n")
        result = _build_diagram_id_to_relpath(diagrams_dir=diagrams, registry=object())
        assert "DIAG@1.abc" in result

    def test_skips_underscore_puml_files(self, tmp_path: Path) -> None:
        diagrams = tmp_path / "diagrams"
        diagrams.mkdir()
        (diagrams / "_private.puml").write_text("")
        result = _build_diagram_id_to_relpath(diagrams_dir=diagrams, registry=object())
        assert "_private" not in result

    def test_finds_md_files_with_artifact_id(self, tmp_path: Path) -> None:
        diagrams = tmp_path / "diagrams"
        diagrams.mkdir()
        f = diagrams / "MATRIX@1.abc.md"
        f.write_text("---\nartifact-id: MATRIX@1.abc\n---\nbody\n")
        result = _build_diagram_id_to_relpath(diagrams_dir=diagrams, registry=object())
        assert "MATRIX@1.abc" in result
        assert result["MATRIX@1.abc"] == "MATRIX@1.abc.md"

    def test_skips_underscore_md_files(self, tmp_path: Path) -> None:
        diagrams = tmp_path / "diagrams"
        diagrams.mkdir()
        (diagrams / "_index.md").write_text("")
        result = _build_diagram_id_to_relpath(diagrams_dir=diagrams, registry=object())
        assert "_index" not in result

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        result = _build_diagram_id_to_relpath(diagrams_dir=tmp_path / "nodir", registry=object())
        assert result == {}

    def test_stem_fallback_for_md_without_artifact_id(self, tmp_path: Path) -> None:
        diagrams = tmp_path / "diagrams"
        diagrams.mkdir()
        (diagrams / "my-matrix.md").write_text("---\n---\nbody\n")
        result = _build_diagram_id_to_relpath(diagrams_dir=diagrams, registry=object())
        assert "my-matrix" in result


# ---------------------------------------------------------------------------
# _linkify_known_tokens_in_matrix_rows
# ---------------------------------------------------------------------------


class TestLinkifyKnownTokensInMatrixRows:
    def test_replaces_token_in_table_row(self) -> None:
        md = "| DIAG@1.abc | description |\n|---|---|\n"
        mapping = {"DIAG@1.abc": "DIAG@1.abc.md"}
        result, count = _linkify_known_tokens_in_matrix_rows(
            matrix_markdown=md, diagram_id_to_relpath=mapping
        )
        assert "[DIAG@1.abc](DIAG@1.abc.md)" in result
        assert count == 1

    def test_skips_header_separator_rows(self) -> None:
        md = "|---|---|\n"
        mapping = {"foo": "foo.md"}
        result, count = _linkify_known_tokens_in_matrix_rows(matrix_markdown=md, diagram_id_to_relpath=mapping)
        assert count == 0

    def test_skips_already_linked_rows(self) -> None:
        md = "| [foo](foo.md) | desc |\n"
        mapping = {"foo": "foo.md"}
        result, count = _linkify_known_tokens_in_matrix_rows(matrix_markdown=md, diagram_id_to_relpath=mapping)
        assert count == 0

    def test_returns_unchanged_when_empty_mapping(self) -> None:
        md = "| foo | bar |\n"
        result, count = _linkify_known_tokens_in_matrix_rows(matrix_markdown=md, diagram_id_to_relpath={})
        assert result == md
        assert count == 0

    def test_multiple_distinct_tokens_replaced(self) -> None:
        md = "| alpha | beta |\n"
        mapping = {"alpha": "alpha.md", "beta": "beta.md"}
        result, count = _linkify_known_tokens_in_matrix_rows(matrix_markdown=md, diagram_id_to_relpath=mapping)
        assert "[alpha](alpha.md)" in result
        assert "[beta](beta.md)" in result
        assert count == 2

    def test_non_table_rows_unchanged(self) -> None:
        md = "# Header\nsome text\n| row | data |\n"
        mapping = {"row": "row.md"}
        result, _ = _linkify_known_tokens_in_matrix_rows(matrix_markdown=md, diagram_id_to_relpath=mapping)
        assert result.startswith("# Header")


# ---------------------------------------------------------------------------
# _linkify_matrix_ids
# ---------------------------------------------------------------------------


class TestLinkifyMatrixIds:
    def _eng_root(self, tmp_path: Path) -> Path:
        return tmp_path / "engagements" / "ENG-MAT" / "architecture-repository"

    def _write_entity(self, root: Path, artifact_id: str, name: str) -> None:
        entity_dir = root / "model" / "motivation" / "requirement"
        entity_dir.mkdir(parents=True, exist_ok=True)
        path = entity_dir / f"{artifact_id}.md"
        path.write_text(f"---\nartifact-id: {artifact_id}\nname: {name}\n---\n")

    def test_replaces_entity_id_with_link(self, tmp_path: Path) -> None:
        root = self._eng_root(tmp_path)
        eid = "REQ@1000000230.MatLnk.mat-lnk"
        self._write_entity(root, eid, "Mat Link")
        registry = ArtifactRegistry(shared_artifact_index([root]))
        md = f"| {eid} | description |\n|---|\n"
        result, count = _linkify_matrix_ids(
            repo_root=root,
            registry=registry,
            matrix_markdown=md,
            candidate_entity_ids=[eid],
        )
        assert "[Mat Link]" in result or eid in result
        assert count >= 1

    def test_no_match_returns_unchanged(self, tmp_path: Path) -> None:
        root = self._eng_root(tmp_path)
        root.mkdir(parents=True)
        registry = ArtifactRegistry(shared_artifact_index([root]))
        md = "| REQ@9.ZZZ.no-such | description |\n"
        result, count = _linkify_matrix_ids(
            repo_root=root,
            registry=registry,
            matrix_markdown=md,
            candidate_entity_ids=["REQ@9.ZZZ.no-such"],
        )
        assert count == 0
        assert result == md

    def test_no_candidate_ids_returns_unchanged(self, tmp_path: Path) -> None:
        root = self._eng_root(tmp_path)
        root.mkdir(parents=True)
        registry = ArtifactRegistry(shared_artifact_index([root]))
        md = "| some content |\n"
        result, count = _linkify_matrix_ids(
            repo_root=root,
            registry=registry,
            matrix_markdown=md,
            candidate_entity_ids=[],
        )
        assert result == md
        assert count == 0
