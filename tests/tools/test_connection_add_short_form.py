"""Short-form endpoint ids passed to add_connection must be canonicalized to the full
(PREFIX@epoch.random.slug) form in the persisted outgoing file — the read model joins a
connection's endpoints to entity records by full id, so a short form written verbatim
(especially as a fresh file's ``source-entity``) produces a connection that is indexed
but never joins to its endpoints (invisible to traversal and viewpoints)."""

from __future__ import annotations

from pathlib import Path

from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.write.artifact_write.connection import add_connection


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    slug = artifact_id.split(".")[-1]
    prefix = artifact_id.split("@")[0]
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
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


def test_short_form_ids_are_canonicalized_in_a_fresh_outgoing_file(tmp_path: Path) -> None:
    root = tmp_path / "engagements" / "ENG-SHORT" / "architecture-repository"
    src = "REQ@1000000310.ShrtA1.source-entity"
    tgt = "REQ@1000000311.ShrtB2.target-entity"
    _write(root / "model" / "motivation" / "requirement" / f"{src}.md", _entity_md(src, "Source"))
    _write(root / "model" / "motivation" / "requirement" / f"{tgt}.md", _entity_md(tgt, "Target"))
    registry = ArtifactRegistry(shared_artifact_index([root]))
    verifier = ArtifactVerifier(registry, catalogs=build_runtime_catalogs(get_module_registry()))

    result = add_connection(
        repo_root=root,
        registry=registry,
        verifier=verifier,
        clear_repo_caches=lambda p: None,
        source_entity="REQ@1000000310.ShrtA1",  # short form
        connection_type="archimate-association",
        target_entity="REQ@1000000311.ShrtB2",  # short form
        description="Short-form endpoints must persist full.",
        version="0.1.0",
        status="draft",
        last_updated=None,
        dry_run=True,
    )

    assert result.content is not None
    assert f"source-entity: {src}" in result.content
    assert f"### archimate-association → {tgt}" in result.content
