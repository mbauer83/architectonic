"""Tests for entity_edit.py — promote_entity, rename collision, group move.

Covers the promote_entity function (status lifecycle) and the
_resolve_target_identity error path (rename collision).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.entity_edit import promote_entity

# ── helpers ───────────────────────────────────────────────────────────────────


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str, status: str = "draft") -> str:
    slug = artifact_id.split(".")[-1].replace("-", "_")
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: {status}
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

Entity for promote testing.

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
alias: REQ_{slug}
```
"""


def _setup_engagement(tmp_path: Path, tag: str) -> Path:
    return tmp_path / "engagements" / f"ENG-{tag}" / "architecture-repository"


def _build_write_deps(repo_root: Path) -> tuple[ArtifactRegistry, ArtifactVerifier]:
    registry = ArtifactRegistry(shared_artifact_index([repo_root]))
    verifier = ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))
    return registry, verifier


# ── promote_entity ────────────────────────────────────────────────────────────


class TestPromoteEntity:
    def test_promote_draft_to_active_dry_run(self, tmp_path: Path) -> None:
        root = _setup_engagement(tmp_path, "PRM1")
        eid = "REQ@1000000090.EntPrm1.promote-draft"
        _write(root / "model" / "motivation" / "requirement" / f"{eid}.md", _entity_md(eid, "Draft Entity", "draft"))
        registry, verifier = _build_write_deps(root)
        result = promote_entity(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            artifact_id=eid,
            dry_run=True,
        )
        assert result.wrote is False
        # Status would change to 'active'
        assert "active" in (result.content or "")

    def test_promote_active_to_deprecated_dry_run(self, tmp_path: Path) -> None:
        root = _setup_engagement(tmp_path, "PRM2")
        eid = "REQ@1000000091.EntPrm2.promote-active"
        _write(root / "model" / "motivation" / "requirement" / f"{eid}.md", _entity_md(eid, "Active Entity", "active"))
        registry, verifier = _build_write_deps(root)
        result = promote_entity(
            repo_root=root,
            registry=registry,
            verifier=verifier,
            clear_repo_caches=lambda p: None,
            artifact_id=eid,
            dry_run=True,
        )
        assert result.wrote is False
        assert "deprecated" in (result.content or "")

    def test_promote_deprecated_raises_value_error(self, tmp_path: Path) -> None:
        root = _setup_engagement(tmp_path, "PRM3")
        eid = "REQ@1000000092.EntPrm3.promote-deprecated"
        _write(
            root / "model" / "motivation" / "requirement" / f"{eid}.md",
            _entity_md(eid, "Deprecated Entity", "deprecated"),
        )
        registry, verifier = _build_write_deps(root)
        with pytest.raises(ValueError, match="terminal"):
            promote_entity(
                repo_root=root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                artifact_id=eid,
                dry_run=True,
            )

    def test_promote_not_found_raises_value_error(self, tmp_path: Path) -> None:
        root = _setup_engagement(tmp_path, "PRM4")
        root.mkdir(parents=True)
        registry, verifier = _build_write_deps(root)
        with pytest.raises(ValueError, match="not found"):
            promote_entity(
                repo_root=root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                artifact_id="REQ@9.ZZZ.no-such",
                dry_run=True,
            )
