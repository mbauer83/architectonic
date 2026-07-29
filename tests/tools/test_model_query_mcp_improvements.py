"""Tests for model query MCP improvements.

Updated for ArchiMate 4.0 conventions:
- model/ directory (not model-entities/)
- New ID format: TYPE@epoch.random.friendly-name
- New frontmatter: removed engagement, phase-produced, owner-agent, safety-relevant
- Standard YAML frontmatter for diagrams (not comment-style)
"""

from pathlib import Path

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp import mcp_artifact_server


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_repo(root: Path) -> Path:
    _write(
        root / "model" / "application" / "application-component" / "APP@1712870400.kRZYOA.event-store.md",
        """---
artifact-id: APP@1712870400.kRZYOA.event-store
artifact-type: application-component
name: "Event Store"
version: 0.1.0
status: draft
keywords: [events, storage]
last-updated: '2026-04-14'
---

<!-- §content -->

## Event Store

Stores event streams.

## Properties

| Attribute | Value |
|---|---|
| (none) | (none) |

<!-- §display -->

### archimate

```yaml
domain: Application
element-type: ApplicationComponent
label: "Event Store"
alias: APP_kRZYOA
```
""",
    )
    _write(
        root / "diagram-catalog" / "diagrams" / "DIA@1712870400.DFgOaO.event-activity-overview.puml",
        """---
artifact-id: DIA@1712870400.DFgOaO.event-activity-overview
artifact-type: diagram
name: "Event Activity Overview"
diagram-type: activity
version: 0.1.0
status: draft
last-updated: '2026-04-14'
---
@startuml
title Event Activity Overview
@enduml
""",
    )
    return root


def test_model_repository_search_priority_and_counts(tmp_path: Path) -> None:
    repo_root = _build_repo(tmp_path / "repo")
    repo = ArtifactRepository(shared_artifact_index(repo_root))

    strict = repo.search_artifacts(
        "event",
        prefer_record_type="diagram",
        strict_record_type=True,
        include_connections=False,
        include_diagrams=True,
    )
    assert strict.hits
    assert all(hit.record_type == "diagram" for hit in strict.hits)

    preferred = repo.search_artifacts(
        "event",
        prefer_record_type="diagram",
        strict_record_type=False,
        include_connections=False,
        include_diagrams=True,
    )
    assert preferred.hits
    assert preferred.hits[0].record_type == "diagram"

    counts = repo.count_artifacts_by("diagram_type", include_connections=False, include_diagrams=True)
    assert counts["activity"] == 1


def test_model_query_mcp_projection_and_aggregate_tool(tmp_path: Path) -> None:
    repo_root = _build_repo(tmp_path / "repo")
    tool_map = mcp_artifact_server.mcp_read._tool_manager._tools

    listed = tool_map["artifact_query_list_artifacts"].fn(
        repo_root=str(repo_root),
        repo_scope="engagement",
        include_record_types=["entities"],
        fields=["artifact_id", "path"],
    )
    assert listed
    assert set(listed[0].keys()) == {"artifact_id", "path"}

    searched = tool_map["artifact_query_search_artifacts"].fn(
        "event",
        repo_root=str(repo_root),
        repo_scope="engagement",
        fields=["artifact_id", "record_type", "score"],
        include_record_types=["entities", "diagrams", "documents"],
        prefer_record_type="diagram",
    )
    assert searched["hits"]
    assert set(searched["hits"][0].keys()) <= {"artifact_id", "record_type", "score"}

    grouped = tool_map["artifact_query_stats"].fn(
        group_by="diagram_type",
        repo_root=str(repo_root),
        repo_scope="engagement",
    )
    assert grouped["counts"]["activity"] == 1


def test_read_artifact_resolves_short_form_id(tmp_path: Path) -> None:
    """artifact_query_read_artifact must not error when given a 2-segment short-form ID.

    Regression: ArtifactRepository was missing entity_ids()/connection_ids() delegation
    causing 'ArtifactRepository object has no attribute entity_ids' for short-form IDs.
    """
    repo_root = _build_repo(tmp_path / "repo")
    tool_map = mcp_artifact_server.mcp_read._tool_manager._tools

    # Full-form ID works
    full = tool_map["artifact_query_read_artifact"].fn(
        "APP@1712870400.kRZYOA.event-store",
        repo_root=str(repo_root),
        repo_scope="engagement",
    )
    assert full["artifact_id"] == "APP@1712870400.kRZYOA.event-store"

    # Short-form ID (2 segments) must resolve to the same entity without raising
    short = tool_map["artifact_query_read_artifact"].fn(
        "APP@1712870400.kRZYOA",
        repo_root=str(repo_root),
        repo_scope="engagement",
    )
    assert short["artifact_id"] == "APP@1712870400.kRZYOA.event-store"


def test_list_and_read_carry_the_modification_stamp(tmp_path: Path) -> None:
    """An agent deciding what changed recently needs the stamp on both the list and the read.

    It is projectable by name, so `fields=['artifact_id', 'last_updated']` is a usable
    "what moved lately" query without pulling whole artifacts.
    """
    repo_root = _build_repo(tmp_path / "repo")
    tool_map = mcp_artifact_server.mcp_read._tool_manager._tools

    listed = tool_map["artifact_query_list_artifacts"].fn(
        repo_root=str(repo_root),
        repo_scope="engagement",
        include_record_types=["entities", "diagrams"],
        fields=["artifact_id", "last_updated"],
    )
    stamps = {row["artifact_id"]: row["last_updated"] for row in listed}
    assert stamps["APP@1712870400.kRZYOA.event-store"] == "2026-04-14"

    read = tool_map["artifact_query_read_artifact"].fn(
        "APP@1712870400.kRZYOA.event-store",
        repo_root=str(repo_root),
        repo_scope="engagement",
    )
    assert read["last_updated"] == "2026-04-14"
