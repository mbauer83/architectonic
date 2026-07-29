"""Tests for repo_path_helpers.py pure path derivation functions.

Covers: group_fn_entity, group_fn_diagram, group_fn_document, group_fn,
repo_root_for_model_path, repo_root_for_diagram_path, rendered_path_for.
"""

from __future__ import annotations

from pathlib import Path

from src.application.repo_path_helpers import (
    group_fn,
    group_fn_diagram,
    group_fn_document,
    group_fn_entity,
    rendered_dir_for_diagram,
    rendered_path_for,
    repo_root_for_diagram_path,
    repo_root_for_model_path,
)
from src.domain.repository.groups import UNCATEGORIZED

# ---------------------------------------------------------------------------
# group_fn_entity
# ---------------------------------------------------------------------------


class TestGroupFnEntity:
    def test_legacy_model_path_returns_uncategorized(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        entity = repo / "model" / "Motivation" / "capability" / "ENT@1.abc.md"
        assert group_fn_entity(entity, repo) == UNCATEGORIZED

    def test_target_layout_returns_slug(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        entity = repo / "projects" / "my-proj" / "model" / "Motivation" / "capability" / "ENT@1.abc.md"
        assert group_fn_entity(entity, repo) == "my-proj"

    def test_path_outside_repo_returns_uncategorized(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        entity = tmp_path / "other" / "file.md"
        assert group_fn_entity(entity, repo) == UNCATEGORIZED

    def test_empty_rel_parts_returns_uncategorized(self, tmp_path: Path) -> None:
        # Unlikely in practice but guard the empty-parts branch
        repo = tmp_path
        assert group_fn_entity(repo, repo) == UNCATEGORIZED


# ---------------------------------------------------------------------------
# group_fn_diagram
# ---------------------------------------------------------------------------


class TestGroupFnDiagram:
    def test_legacy_flat_diagram_returns_uncategorized(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        diag = repo / "diagram-catalog" / "diagrams" / "DIAG@1.abc.puml"
        assert group_fn_diagram(diag, repo) == UNCATEGORIZED

    def test_collection_diagram_returns_slug(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        diag = repo / "diagram-catalog" / "diagrams" / "my-collection" / "DIAG@1.abc.puml"
        assert group_fn_diagram(diag, repo) == "my-collection"

    def test_path_outside_diagrams_returns_uncategorized(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        diag = tmp_path / "other" / "diagram.puml"
        assert group_fn_diagram(diag, repo) == UNCATEGORIZED

    def test_confidential_flat_diagram_returns_uncategorized(self, tmp_path: Path) -> None:
        """Regression: the 'confidential' segment itself was misread as the group slug."""
        repo = tmp_path / "repo"
        diag = repo / "diagram-catalog" / "diagrams" / "confidential" / "DIAG@1.abc.puml"
        assert group_fn_diagram(diag, repo) == UNCATEGORIZED

    def test_confidential_collection_diagram_returns_slug(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        diag = repo / "diagram-catalog" / "diagrams" / "confidential" / "assurance" / "DIAG@1.abc.puml"
        assert group_fn_diagram(diag, repo) == "assurance"


# ---------------------------------------------------------------------------
# group_fn_document
# ---------------------------------------------------------------------------


class TestGroupFnDocument:
    def test_legacy_flat_doc_returns_uncategorized(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        doc = repo / "docs" / "adr" / "decision.md"
        assert group_fn_document(doc, repo) == UNCATEGORIZED

    def test_collection_doc_returns_slug(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        doc = repo / "docs" / "adr" / "my-collection" / "decision.md"
        assert group_fn_document(doc, repo) == "my-collection"

    def test_path_outside_docs_returns_uncategorized(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        doc = tmp_path / "other" / "file.md"
        assert group_fn_document(doc, repo) == UNCATEGORIZED


# ---------------------------------------------------------------------------
# group_fn (dispatch)
# ---------------------------------------------------------------------------


class TestGroupFn:
    def test_entity_in_model_dispatches_to_entity(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        entity = repo / "model" / "ENT@1.abc.md"
        assert group_fn(entity, repo) == UNCATEGORIZED

    def test_entity_in_projects_dispatches_to_entity(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        entity = repo / "projects" / "slug" / "model" / "ENT@1.abc.md"
        assert group_fn(entity, repo) == "slug"

    def test_diagram_in_catalog_dispatches_to_diagram(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        diag = repo / "diagram-catalog" / "diagrams" / "coll" / "DIAG.puml"
        assert group_fn(diag, repo) == "coll"

    def test_doc_in_docs_dispatches_to_document(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        doc = repo / "docs" / "adr" / "coll" / "doc.md"
        assert group_fn(doc, repo) == "coll"

    def test_unclassifiable_path_returns_uncategorized(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        unknown = repo / "unknown" / "file.txt"
        assert group_fn(unknown, repo) == UNCATEGORIZED

    def test_path_outside_repo_returns_uncategorized(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        outside = tmp_path / "other" / "file.md"
        assert group_fn(outside, repo) == UNCATEGORIZED

    def test_empty_rel_parts_returns_uncategorized(self, tmp_path: Path) -> None:
        repo = tmp_path
        assert group_fn(repo, repo) == UNCATEGORIZED


# ---------------------------------------------------------------------------
# repo_root_for_model_path
# ---------------------------------------------------------------------------


class TestRepoRootForModelPath:
    def test_finds_root_for_legacy_layout(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        model_path = repo / "model" / "Motivation" / "capability" / "ENT@1.abc.md"
        result = repo_root_for_model_path(model_path)
        assert result == repo

    def test_returns_none_when_no_model_segment(self, tmp_path: Path) -> None:
        path = tmp_path / "other" / "file.md"
        # No "model" segment in path
        result = repo_root_for_model_path(path)
        assert result is None


# ---------------------------------------------------------------------------
# repo_root_for_diagram_path
# ---------------------------------------------------------------------------


class TestRepoRootForDiagramPath:
    def test_finds_root_when_diagram_catalog_exists(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        (repo / "diagram-catalog").mkdir(parents=True)
        diag = repo / "diagram-catalog" / "diagrams" / "DIAG@1.abc.puml"
        result = repo_root_for_diagram_path(diag)
        assert result == repo

    def test_returns_none_when_no_diagram_catalog(self, tmp_path: Path) -> None:
        diag = tmp_path / "some" / "path" / "DIAG@1.abc.puml"
        result = repo_root_for_diagram_path(diag)
        assert result is None


# ---------------------------------------------------------------------------
# rendered_dir_for_diagram and rendered_path_for
# ---------------------------------------------------------------------------


class TestRenderedDirForDiagram:
    def test_collection_diagram_dir(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        diag = repo / "diagram-catalog" / "diagrams" / "my-coll" / "DIAG@1.puml"
        result = rendered_dir_for_diagram(diag, repo)
        # Should be rendered/my-coll/
        assert "my-coll" in str(result)

    def test_legacy_flat_diagram_dir(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        diag = repo / "diagram-catalog" / "diagrams" / "DIAG@1.puml"
        result = rendered_dir_for_diagram(diag, repo)
        assert result is not None


class TestRenderedPathFor:
    def test_returns_png_path(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        diag = repo / "diagram-catalog" / "diagrams" / "coll" / "DIAG@1.abc.puml"
        result = rendered_path_for(diag, repo)
        assert result.suffix == ".png"
        assert result.stem == "DIAG@1.abc"

    def test_custom_suffix(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        diag = repo / "diagram-catalog" / "diagrams" / "coll" / "DIAG@1.abc.puml"
        result = rendered_path_for(diag, repo, suffix=".svg")
        assert result.suffix == ".svg"
