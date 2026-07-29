"""Integration tests for ranked search correctness (WU-A2).

Verifies:
- Documents reach the top hits when queried by title tokens, even when many entities match.
- Per-kind include-set filtering (documents-only returns no entity hits).
- Minority kind (document) not starved when limit is small.
- ``included_kinds`` excludes entities when "entities" is not in the set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifact_repository import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index

# ── helpers ──────────────────────────────────────────────────────────────────


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str, artifact_type: str = "application-component") -> str:
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

Component description.

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


def _document_md(artifact_id: str, title: str, content: str = "") -> str:
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

{content or "Content placeholder."}
"""


def _build_repo(root: Path, n_entities: int = 20) -> Path:
    """Repo with one coding-guidelines document + N application components."""
    doc_id = "STD@1712870400.CDGLN0.general-coding-guidelines"
    _write(
        root / "docs" / "standards" / f"{doc_id}.md",
        _document_md(
            doc_id,
            "General Coding Guidelines",
            "These coding guidelines cover style, naming, formatting.",
        ),
    )
    for i in range(n_entities):
        eid = f"APP@1712870400.ENT{i:03d}.service-component-{i}"
        _write(
            root / "model" / "application" / "application-component" / f"{eid}.md",
            _entity_md(eid, f"Service Component {i}"),
        )
    return root


# ── tests ────────────────────────────────────────────────────────────────────


def test_document_reaches_top_hits_for_title_tokens(tmp_path: Path) -> None:
    """A document whose title contains both query words must appear in search results.

    Regression for the pre-fix behaviour where the FTS entity flood prevented the
    coding-guidelines document from ever appearing (the fallback scored path only
    fired when FTS returned zero hits overall, but entities always had hits).
    """
    root = _build_repo(tmp_path / "repo", n_entities=30)
    repo = ArtifactRepository(shared_artifact_index(root))

    result = repo.search_artifacts("coding guidelines", limit=10)

    hit_ids = [h.record.artifact_id for h in result.hits]
    assert any("general-coding-guidelines" in aid for aid in hit_ids), (
        f"Document not in hits. Got: {hit_ids}"
    )


def test_documents_only_include_set_returns_no_entities(tmp_path: Path) -> None:
    """``include_record_types=['documents']`` must return only document hits."""
    root = _build_repo(tmp_path / "repo", n_entities=10)
    repo = ArtifactRepository(shared_artifact_index(root))

    result = repo.search_artifacts(
        "coding guidelines service component",
        limit=20,
        include_entities=False,
        include_connections=False,
        include_diagrams=False,
        include_documents=True,
    )

    assert all(h.record_type == "document" for h in result.hits), (
        f"Non-document hits returned: {[h.record_type for h in result.hits]}"
    )


def test_entities_only_include_set_returns_no_documents(tmp_path: Path) -> None:
    """``include_entities=True, include_documents=False`` returns no document hits."""
    root = _build_repo(tmp_path / "repo", n_entities=5)
    repo = ArtifactRepository(shared_artifact_index(root))

    result = repo.search_artifacts(
        "coding guidelines",
        limit=20,
        include_entities=True,
        include_connections=False,
        include_diagrams=False,
        include_documents=False,
    )

    assert all(h.record_type == "entity" for h in result.hits), (
        f"Unexpected hit types: {[h.record_type for h in result.hits]}"
    )


def test_minority_kind_not_starved_by_limit(tmp_path: Path) -> None:
    """A single relevant document must appear even when limit < number of entity hits.

    Verifies that per-kind FTS limits prevent a dominant kind from consuming all
    available result slots.
    """
    root = _build_repo(tmp_path / "repo", n_entities=50)
    repo = ArtifactRepository(shared_artifact_index(root))

    # With only limit=5, entity hits could fill all slots under the old design.
    result = repo.search_artifacts("coding guidelines", limit=5)

    hit_ids = [h.record.artifact_id for h in result.hits]
    assert any("general-coding-guidelines" in aid for aid in hit_ids), (
        f"Document starved out. Hits (limit=5): {hit_ids}"
    )


@pytest.mark.parametrize("query", ["coding", "guidelines", "coding guidelines"])
def test_document_searchable_by_title_tokens(tmp_path: Path, query: str) -> None:
    """Each title token and the full title phrase should return the document."""
    root = _build_repo(tmp_path / "repo", n_entities=5)
    repo = ArtifactRepository(shared_artifact_index(root))

    result = repo.search_artifacts(query, limit=20, include_entities=False, include_documents=True)

    assert result.hits, f"No hits for query '{query}'"
    assert all(h.record_type == "document" for h in result.hits)
