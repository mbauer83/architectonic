"""Tests for connection.py — error paths in add_connection.

Covers: unknown connection type, missing source/target entity,
duplicate connection detection, and junction homogeneity enforcement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.connection import add_connection

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


def _junction_md(artifact_id: str, name: str, junction_type: str = "and-junction") -> str:
    slug = artifact_id.split(".")[-1]
    prefix = artifact_id.split("@")[0]
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: {junction_type}
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

Junction entity.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Motivation
element-type: Junction
label: "{name}"
alias: {prefix}_{slug}
```
"""


def _outgoing_md(source_id: str, connection_type: str, target_id: str) -> str:
    return f"""\
---
artifact-id: {source_id}
artifact-type: outgoing
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

### {connection_type} → {target_id}
"""


def _build_deps(repo_root: Path) -> tuple[ArtifactRegistry, ArtifactVerifier]:
    registry = ArtifactRegistry(shared_artifact_index([repo_root]))
    verifier = ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))
    return registry, verifier


# ── unknown connection type ───────────────────────────────────────────────────


class TestAddConnectionUnknownType:
    def test_unknown_type_raises_value_error(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "ACTE1")
        src = "REQ@1000000210.AcErr1.src"
        tgt = "REQ@1000000211.AcErr2.tgt"
        _write(root / "model" / "motivation" / "requirement" / f"{src}.md", _entity_md(src, "Src"))
        _write(root / "model" / "motivation" / "requirement" / f"{tgt}.md", _entity_md(tgt, "Tgt"))
        registry, verifier = _build_deps(root)
        with pytest.raises(ValueError, match="Unknown connection type"):
            add_connection(
                repo_root=root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                source_entity=src,
                connection_type="nonexistent-conn-type",
                target_entity=tgt,
                description=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )


# ── missing source/target ─────────────────────────────────────────────────────


class TestAddConnectionMissingEntities:
    def test_source_not_found_raises_value_error(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "ACTE2")
        tgt = "REQ@1000000212.AcErr3.tgt"
        _write(root / "model" / "motivation" / "requirement" / f"{tgt}.md", _entity_md(tgt, "Tgt"))
        registry, verifier = _build_deps(root)
        with pytest.raises(ValueError, match="not found"):
            add_connection(
                repo_root=root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                source_entity="REQ@9.ZZZ.missing-src",
                connection_type="archimate-association",
                target_entity=tgt,
                description=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )

    def test_target_not_found_raises_value_error(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "ACTE3")
        src = "REQ@1000000213.AcErr4.src"
        _write(root / "model" / "motivation" / "requirement" / f"{src}.md", _entity_md(src, "Src"))
        registry, verifier = _build_deps(root)
        with pytest.raises(ValueError, match="not found"):
            add_connection(
                repo_root=root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                source_entity=src,
                connection_type="archimate-association",
                target_entity="REQ@9.ZZZ.missing-tgt",
                description=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )


# ── duplicate connection detection ────────────────────────────────────────────


class TestAddConnectionDuplicate:
    def test_duplicate_raises_value_error(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "ACTE4")
        src = "REQ@1000000214.DupSrc.dup-src"
        tgt = "REQ@1000000215.DupTgt.dup-tgt"
        _write(root / "model" / "motivation" / "requirement" / f"{src}.md", _entity_md(src, "Dup Src"))
        _write(root / "model" / "motivation" / "requirement" / f"{tgt}.md", _entity_md(tgt, "Dup Tgt"))
        _write(
            root / "model" / "motivation" / "requirement" / f"{src}.outgoing.md",
            _outgoing_md(src, "archimate-association", tgt),
        )
        registry, verifier = _build_deps(root)
        with pytest.raises(ValueError, match="already exists"):
            add_connection(
                repo_root=root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                source_entity=src,
                connection_type="archimate-association",
                target_entity=tgt,
                description=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )

    def test_duplicate_with_multiplicity_strips_and_matches(self, tmp_path: Path) -> None:
        """Duplicate check should strip multiplicities before comparing targets."""
        root = _eng_root(tmp_path, "ACTE5")
        src = "REQ@1000000216.DupCard.dup-card"
        tgt = "REQ@1000000217.DupCardTgt.dup-card-tgt"
        _write(root / "model" / "motivation" / "requirement" / f"{src}.md", _entity_md(src, "Dup Card"))
        _write(root / "model" / "motivation" / "requirement" / f"{tgt}.md", _entity_md(tgt, "Dup Card Tgt"))
        # Write outgoing file with multiplicity syntax
        outgoing_text = f"""\
---
artifact-id: {src}
artifact-type: outgoing
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

### archimate-association [1] → [*] {tgt}
"""
        _write(
            root / "model" / "motivation" / "requirement" / f"{src}.outgoing.md",
            outgoing_text,
        )
        registry, verifier = _build_deps(root)
        with pytest.raises(ValueError, match="already exists"):
            add_connection(
                repo_root=root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                source_entity=src,
                connection_type="archimate-association",
                target_entity=tgt,
                description=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )


# ── junction homogeneity enforcement ──────────────────────────────────────────


class TestJunctionHomogeneity:
    def test_mixed_type_raises_value_error(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "JUNC1")
        junc = "AND@1000000218.Junc1.junc-one"
        tgt = "REQ@1000000219.JuncTgt.junc-tgt"
        _write(root / "model" / "motivation" / "and-junction" / f"{junc}.md", _junction_md(junc, "Junc One"))
        _write(root / "model" / "motivation" / "requirement" / f"{tgt}.md", _entity_md(tgt, "Junc Tgt"))
        # Pre-write outgoing with archimate-association
        _write(
            root / "model" / "motivation" / "and-junction" / f"{junc}.outgoing.md",
            _outgoing_md(junc, "archimate-association", tgt),
        )
        registry, verifier = _build_deps(root)
        new_tgt = "REQ@1000000220.JuncTgt2.junc-tgt-two"
        _write(root / "model" / "motivation" / "requirement" / f"{new_tgt}.md", _entity_md(new_tgt, "Junc Tgt 2"))
        registry2, verifier2 = _build_deps(root)
        with pytest.raises(ValueError, match="locked to connection type"):
            add_connection(
                repo_root=root,
                registry=registry2,
                verifier=verifier2,
                clear_repo_caches=lambda p: None,
                source_entity=junc,
                connection_type="archimate-influence",
                target_entity=new_tgt,
                description=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
            )

    def test_multiplicity_at_junction_raises_value_error(self, tmp_path: Path) -> None:
        root = _eng_root(tmp_path, "JUNC2")
        junc = "AND@1000000221.Junc2.junc-two"
        tgt = "REQ@1000000222.JuncTgt3.junc-tgt-three"
        _write(root / "model" / "motivation" / "and-junction" / f"{junc}.md", _junction_md(junc, "Junc Two"))
        _write(root / "model" / "motivation" / "requirement" / f"{tgt}.md", _entity_md(tgt, "Junc Tgt 3"))
        registry, verifier = _build_deps(root)
        with pytest.raises(ValueError, match="Multiplicities are not permitted"):
            add_connection(
                repo_root=root,
                registry=registry,
                verifier=verifier,
                clear_repo_caches=lambda p: None,
                source_entity=junc,
                connection_type="archimate-association",
                target_entity=tgt,
                description=None,
                version="0.1.0",
                status="draft",
                last_updated=None,
                dry_run=True,
                src_multiplicity="1",
            )
