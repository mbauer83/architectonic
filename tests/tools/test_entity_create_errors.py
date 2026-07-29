"""Tests for entity.py — error paths in create_entity.

Covers: GAR type rejection, duplicate slug detection,
and _render_display fallback when ontology is None.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.entity import create_entity

# ── helpers ───────────────────────────────────────────────────────────────────


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _eng_root(tmp_path: Path, tag: str) -> Path:
    return tmp_path / "engagements" / f"ENG-{tag}" / "architecture-repository"


def _entity_md(artifact_id: str, name: str, artifact_type: str = "requirement") -> str:
    slug = artifact_id.split(".")[-1]
    prefix = artifact_id.split("@")[0]
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {artifact_type}
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

Test entity.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Requirement
label: "{name}"
alias: {prefix}_{slug}
```
"""


def _build_verifier(repo_root: Path) -> ArtifactVerifier:
    registry = ArtifactRegistry(shared_artifact_index([repo_root]))
    return ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))


# ── GAR type rejection ────────────────────────────────────────────────────────


class TestCreateEntityGARRejection:
    def test_gar_type_raises_value_error(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "GAR1")
        root.mkdir(parents=True)
        verifier = _build_verifier(root)
        with pytest.raises(ValueError, match="global-artifact-reference"):
            create_entity(
                repo_root=root,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                artifact_type="global-artifact-reference",
                name="Should Not Create",
                summary=None,
                properties=None,
                notes=None,
                artifact_id=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )


# ── duplicate slug detection ──────────────────────────────────────────────────


class TestCreateEntityDuplicateSlug:
    def test_duplicate_name_returns_error_result(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "DUP1")
        eid = "REQ@1000000200.DupSlg1.dup-slug-one"
        _write(
            root / "model" / "motivation" / "requirement" / f"{eid}.md",
            _entity_md(eid, "Dup Slug One"),
        )
        verifier = _build_verifier(root)
        result = create_entity(
            repo_root=root,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            artifact_type="requirement",
            name="Dup Slug One",
            summary=None,
            properties=None,
            notes=None,
            artifact_id=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=True,
        )
        assert result.wrote is False
        assert result.warnings
        assert any("already exists" in w for w in result.warnings)

    def test_duplicate_slug_verification_has_error_code(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "DUP2")
        eid = "REQ@1000000201.DupSlg2.dup-slug-two"
        _write(
            root / "model" / "motivation" / "requirement" / f"{eid}.md",
            _entity_md(eid, "Dup Slug Two"),
        )
        verifier = _build_verifier(root)
        result = create_entity(
            repo_root=root,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            artifact_type="requirement",
            name="Dup Slug Two",
            summary=None,
            properties=None,
            notes=None,
            artifact_id=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=True,
        )
        assert result.verification is not None
        issues = result.verification.get("issues", [])
        codes = [i.get("code") for i in issues]
        assert "duplicate_artifact" in codes


# ── _render_display with no ontology ─────────────────────────────────────────


class TestRenderDisplayFallback:
    def test_no_ontology_falls_back_to_archimate_display(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "RDS1")
        root.mkdir(parents=True)
        verifier = _build_verifier(root)
        real_reg = get_module_registry()
        with patch.object(real_reg, "ontology_for_entity_type", return_value=None), \
             patch("src.infrastructure.app_bootstrap.get_module_registry", return_value=real_reg):
            result = create_entity(
                repo_root=root,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                artifact_type="requirement",
                name="No Ontology Entity",
                summary=None,
                properties=None,
                notes=None,
                artifact_id=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )
        assert result.content is not None
        assert "archimate" in result.content


# ── group placement ───────────────────────────────────────────────────────────


class TestCreateEntityGroupPlacement:
    """The group param must place the file under projects/<slug>/model/… — a regression
    silently dropped it on the happy path (only the error branches honored it), landing
    every entity in the legacy uncategorized location regardless of the requested project."""

    def test_group_places_entity_in_project_directory(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "GRP1")
        root.mkdir(parents=True)
        result = create_entity(
            repo_root=root,
            verifier=_build_verifier(root),
            clear_repo_caches=lambda p: None,
            artifact_type="outcome",
            name="Grouped Outcome",
            summary=None,
            properties=None,
            notes=None,
            artifact_id=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=True,
            group="alpha-project",
        )
        rel = result.path.relative_to(root)
        assert rel.parts[:2] == ("projects", "alpha-project"), rel
        assert "model" in rel.parts

    def test_default_group_stays_in_legacy_location(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "GRP2")
        root.mkdir(parents=True)
        result = create_entity(
            repo_root=root,
            verifier=_build_verifier(root),
            clear_repo_caches=lambda p: None,
            artifact_type="outcome",
            name="Ungrouped Outcome",
            summary=None,
            properties=None,
            notes=None,
            artifact_id=None,
            version="0.1.0",
            status="draft",
            last_updated=None,
            dry_run=True,
        )
        assert result.path.relative_to(root).parts[0] == "model"
