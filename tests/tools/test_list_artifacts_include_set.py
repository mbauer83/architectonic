"""Regression tests for list_artifacts include-set filtering (WU-A3).

Verifies that each single-kind filter returns only that kind, combinations work,
and the default (entities-only) is preserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifact_repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: application-component
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §content -->

## {name}

A component.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Application
element-type: ApplicationComponent
label: "{name}"
alias: {artifact_id.replace("@", "_").replace(".", "_")}
```
"""


def _document_md(artifact_id: str, title: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: document
doc-type: standard
name: "{title}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

# {title}

Document content.
"""


def _diagram_md(artifact_id: str, title: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
name: "{title}"
diagram-type: activity
version: 0.1.0
status: draft
last-updated: '2026-01-01'
diagram-entities: {{}}
---
@startuml
title {title}
@enduml
"""


def _outgoing_md(source_id: str, target_id: str) -> str:
    return f"""\
---
source-entity: {source_id}
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §connections -->

### archimate-association → {target_id}
"""


@pytest.fixture()
def repo(tmp_path: Path) -> ArtifactRepository:
    root = tmp_path / "repo"
    src_id = "APP@1000000001.AAAAA0.alpha-service"
    tgt_id = "APP@1000000001.AAAAA1.beta-service"
    doc_id = "STD@1000000001.BBBBB0.alpha-standard"
    diag_id = "ACT@1000000001.CCCCC0.alpha-process"

    _write(root / "model" / "application" / f"{src_id}.md", _entity_md(src_id, "Alpha Service"))
    _write(root / "model" / "application" / f"{tgt_id}.md", _entity_md(tgt_id, "Beta Service"))
    _write(root / "model" / "application" / f"{src_id}.outgoing.md", _outgoing_md(src_id, tgt_id))
    _write(root / "docs" / f"{doc_id}.md", _document_md(doc_id, "Alpha Standard"))
    _write(root / "diagram-catalog" / "diagrams" / f"{diag_id}.md", _diagram_md(diag_id, "Alpha Process"))

    return ArtifactRepository(shared_artifact_index(root))


def test_default_returns_entities_only(repo: ArtifactRepository) -> None:
    """Default call (no include_record_types) returns only entities."""
    summaries = repo.list_artifacts()
    record_types = {s.record_type for s in summaries}
    assert record_types == {"entity"}, f"Got unexpected record types: {record_types}"


def test_entities_only_filter(repo: ArtifactRepository) -> None:
    """include_entities=True, others False → only entities."""
    summaries = repo.list_artifacts(
        include_entities=True,
        include_connections=False,
        include_diagrams=False,
        include_documents=False,
    )
    record_types = {s.record_type for s in summaries}
    assert record_types == {"entity"}, f"Got: {record_types}"
    assert len(summaries) == 2


def test_entities_excluded(repo: ArtifactRepository) -> None:
    """include_entities=False → no entity records in result."""
    summaries = repo.list_artifacts(
        include_entities=False,
        include_connections=True,
        include_diagrams=True,
        include_documents=True,
    )
    record_types = {s.record_type for s in summaries}
    assert "entity" not in record_types, f"Entity leaked into result: {record_types}"


def test_documents_only_filter(repo: ArtifactRepository) -> None:
    """documents-only filter returns only documents, no entities."""
    summaries = repo.list_artifacts(
        include_entities=False,
        include_connections=False,
        include_diagrams=False,
        include_documents=True,
    )
    record_types = {s.record_type for s in summaries}
    assert record_types == {"document"}, f"Got: {record_types}"
    assert len(summaries) == 1


def test_diagrams_only_filter(repo: ArtifactRepository) -> None:
    """diagrams-only filter returns only diagrams."""
    summaries = repo.list_artifacts(
        include_entities=False,
        include_connections=False,
        include_diagrams=True,
        include_documents=False,
    )
    record_types = {s.record_type for s in summaries}
    assert record_types == {"diagram"}, f"Got: {record_types}"
    assert len(summaries) == 1


def test_connections_only_filter(repo: ArtifactRepository) -> None:
    """connections-only filter returns only connections."""
    summaries = repo.list_artifacts(
        include_entities=False,
        include_connections=True,
        include_diagrams=False,
        include_documents=False,
    )
    record_types = {s.record_type for s in summaries}
    assert record_types == {"connection"}, f"Got: {record_types}"
    assert len(summaries) == 1


def test_entities_and_documents_combination(repo: ArtifactRepository) -> None:
    """entities + documents returns exactly those two kinds."""
    summaries = repo.list_artifacts(
        include_entities=True,
        include_connections=False,
        include_diagrams=False,
        include_documents=True,
    )
    record_types = {s.record_type for s in summaries}
    assert record_types == {"entity", "document"}, f"Got: {record_types}"


def test_all_kinds_returns_all(repo: ArtifactRepository) -> None:
    """Requesting all kinds returns all four record types."""
    summaries = repo.list_artifacts(
        include_entities=True,
        include_connections=True,
        include_diagrams=True,
        include_documents=True,
    )
    record_types = {s.record_type for s in summaries}
    assert record_types == {"entity", "connection", "diagram", "document"}, f"Got: {record_types}"
