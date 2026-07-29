"""Tests: diagram-only entities are indexed, searchable, and distinguished from model entities."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application._diagram_entity_extraction import (
    _diagram_entity_content_text,
)
from src.application._diagram_entity_extraction import (
    extract_diagram_entities as _extract_diagram_entities,
)
from src.application.artifact_query import ArtifactRepository
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.infrastructure.artifact_index import shared_artifact_index

# ── helpers ──────────────────────────────────────────────────────────────────


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


_DIAGRAM_ID = "ACT@1234567890.aBcDeF.my-process"
_DIAGRAM_FILE = "diagram-catalog/diagrams/ACT@1234567890.aBcDeF.my-process.md"

_ACTIVITY_DIAGRAM_CONTENT = f"""\
---
artifact-id: {_DIAGRAM_ID}
artifact-type: diagram
name: "My Process"
diagram-type: activity
version: 0.1.0
status: draft
last-updated: '2026-05-09'
diagram-entities:
  swimlane:
    - id: sw-1
      label: Customer
    - id: sw-2
      label: System
  action:
    - id: a1
      label: Submit Form
      lane_id: sw-1
    - id: a2
      label: Process Request
      lane_id: sw-2
  note:
    - id: n1
      text: Attached annotation
      side: right
---
@startuml my-process
title My Process
@enduml
"""

_MODEL_ENTITY_CONTENT = """\
---
artifact-id: BUS@1000000000.XXXXXX.customer-role
artifact-type: role
name: Customer Role
version: 0.1.0
status: draft
keywords: []
last-updated: '2026-05-09'
---

<!-- §content -->
## Customer Role
<!-- §display -->
### archimate
```yaml
domain: Business
element-type: Role
label: "Customer Role"
alias: BUS_XXXXXX
```
"""


def _build_repo(root: Path) -> Path:
    _write(root / _DIAGRAM_FILE, _ACTIVITY_DIAGRAM_CONTENT)
    _write(
        root / "model" / "business" / "role" / "BUS@1000000000.XXXXXX.customer-role.md",
        _MODEL_ENTITY_CONTENT,
    )
    return root


# ── unit tests for extraction helpers ────────────────────────────────────────


def _make_diagram_record(diagram_entities: object) -> DiagramRecord:
    return DiagramRecord(
        artifact_id=_DIAGRAM_ID,
        artifact_type="diagram",
        name="My Process",
        diagram_type="activity",
        version="0.1.0",
        status="draft",
        path=Path("/tmp/my-process.md"),
        extra={"diagram-entities": diagram_entities},
    )


def test_extract_returns_empty_for_no_diagram_entities() -> None:
    diag = _make_diagram_record(None)
    assert _extract_diagram_entities(diag) == []


def test_extract_returns_empty_for_empty_diagram_entities() -> None:
    diag = _make_diagram_record({})
    assert _extract_diagram_entities(diag) == []


def test_extract_ignores_items_without_id() -> None:
    diag = _make_diagram_record({"action": [{"label": "No ID"}]})
    assert _extract_diagram_entities(diag) == []


def test_extract_creates_entity_for_each_item_with_id() -> None:
    diag = _make_diagram_record(
        {
            "swimlane": [{"id": "sw-1", "label": "Lane A"}, {"id": "sw-2", "label": "Lane B"}],
            "action": [{"id": "a1", "label": "Do It"}],
        }
    )
    entities = _extract_diagram_entities(diag)
    assert len(entities) == 3


def test_extract_artifact_id_format() -> None:
    diag = _make_diagram_record({"swimlane": [{"id": "sw-1", "label": "Lane"}]})
    (rec,) = _extract_diagram_entities(diag)
    assert rec.artifact_id == f"{_DIAGRAM_ID}#swimlane/sw-1"


def test_extract_host_diagram_id_set() -> None:
    diag = _make_diagram_record({"action": [{"id": "a1", "label": "Go"}]})
    (rec,) = _extract_diagram_entities(diag)
    assert rec.host_diagram_id == _DIAGRAM_ID


def test_extract_name_from_label() -> None:
    diag = _make_diagram_record({"action": [{"id": "a1", "label": "Submit Form"}]})
    (rec,) = _extract_diagram_entities(diag)
    assert rec.name == "Submit Form"


def test_extract_name_falls_back_to_text_then_id() -> None:
    diag = _make_diagram_record({"note": [{"id": "n1", "text": "My note"}]})
    (rec,) = _extract_diagram_entities(diag)
    assert rec.name == "My note"

    diag2 = _make_diagram_record({"action": [{"id": "a-unnamed"}]})
    (rec2,) = _extract_diagram_entities(diag2)
    assert rec2.name == "a-unnamed"


def test_extract_domain_and_subdomain() -> None:
    diag = _make_diagram_record({"swimlane": [{"id": "sw-1", "label": "L"}]})
    (rec,) = _extract_diagram_entities(diag)
    assert rec.domain == "activity"
    assert rec.subdomain == "swimlane"


def test_extract_artifact_type_is_entity_type_key() -> None:
    diag = _make_diagram_record({"swimlane": [{"id": "sw-1", "label": "L"}]})
    (rec,) = _extract_diagram_entities(diag)
    assert rec.artifact_type == "swimlane"


def test_extract_inherits_version_status_path() -> None:
    diag = _make_diagram_record({"action": [{"id": "a1", "label": "X"}]})
    (rec,) = _extract_diagram_entities(diag)
    assert rec.version == "0.1.0"
    assert rec.status == "draft"
    assert rec.path == Path("/tmp/my-process.md")


def test_content_text_collects_leaf_strings_recursively() -> None:
    item = {
        "id": "d1",
        "condition": "Valid",
        "then_label": "yes",
        "else_label": "no",
    }
    text = _diagram_entity_content_text(item)
    assert "Valid" in text
    assert "yes" in text
    assert "d1" not in text  # id excluded


def test_content_text_excludes_id_field() -> None:
    text = _diagram_entity_content_text({"id": "should-not-appear", "label": "visible"})
    assert "should-not-appear" not in text
    assert "visible" in text


# ── integration tests against a real indexed repo ────────────────────────────


@pytest.fixture()
def repo(tmp_path: Path) -> ArtifactRepository:
    root = _build_repo(tmp_path / "repo")
    return ArtifactRepository(shared_artifact_index(root))


def test_diagram_entities_appear_in_list_artifacts(repo: ArtifactRepository) -> None:
    summaries = repo.list_artifacts()
    aids = {s.artifact_id for s in summaries}
    assert f"{_DIAGRAM_ID}#swimlane/sw-1" in aids
    assert f"{_DIAGRAM_ID}#action/a1" in aids
    assert f"{_DIAGRAM_ID}#note/n1" in aids


def test_model_entity_has_null_host_diagram_id(repo: ArtifactRepository) -> None:
    summaries = repo.list_artifacts()
    model_entity = next(s for s in summaries if s.artifact_id == "BUS@1000000000.XXXXXX.customer-role")
    assert model_entity.host_diagram_id is None


def test_diagram_entity_has_host_diagram_id(repo: ArtifactRepository) -> None:
    summaries = repo.list_artifacts()
    swimlane = next(s for s in summaries if s.artifact_id == f"{_DIAGRAM_ID}#swimlane/sw-1")
    assert swimlane.host_diagram_id == _DIAGRAM_ID


def test_diagram_entity_path_is_diagram_file(repo: ArtifactRepository, tmp_path: Path) -> None:
    summaries = repo.list_artifacts()
    swimlane = next(s for s in summaries if s.artifact_id == f"{_DIAGRAM_ID}#swimlane/sw-1")
    diagram_path = tmp_path / "repo" / _DIAGRAM_FILE
    assert swimlane.path == diagram_path


def test_read_artifact_returns_entity_with_host_diagram_id(repo: ArtifactRepository) -> None:
    result = repo.read_artifact(f"{_DIAGRAM_ID}#swimlane/sw-2")
    assert result is not None
    assert result["host_diagram_id"] == _DIAGRAM_ID
    assert result["artifact_type"] == "swimlane"
    assert result["name"] == "System"
    assert result["record_type"] == "entity"


def test_read_artifact_model_entity_has_no_host_diagram_id(repo: ArtifactRepository) -> None:
    result = repo.read_artifact("BUS@1000000000.XXXXXX.customer-role")
    assert result is not None
    assert "host_diagram_id" not in result


def test_filter_by_artifact_type_swimlane(repo: ArtifactRepository) -> None:
    summaries = repo.list_artifacts(artifact_type="swimlane")
    assert all(s.artifact_type == "swimlane" for s in summaries)
    assert len(summaries) == 2


def test_filter_by_domain_activity(repo: ArtifactRepository) -> None:
    summaries = repo.list_artifacts(domain="activity")
    assert all(s.host_diagram_id is not None for s in summaries)
    assert len(summaries) == 5  # 2 swimlanes + 2 actions + 1 note


def test_fts_search_finds_diagram_entity_by_name(tmp_path: Path) -> None:
    root = _build_repo(tmp_path / "repo")
    idx = shared_artifact_index(root)
    idx.refresh()
    hits = idx.search_fts(
        "Customer",
        limit=10,
        include_connections=False,
        include_diagrams=False,
        include_documents=False,
    )
    artifact_ids = [h[0] for h in hits]
    assert f"{_DIAGRAM_ID}#swimlane/sw-1" in artifact_ids


def test_summarize_artifact_for_diagram_entity(repo: ArtifactRepository) -> None:
    summary = repo.summarize_artifact(f"{_DIAGRAM_ID}#action/a1")
    assert summary is not None
    assert summary.host_diagram_id == _DIAGRAM_ID
    assert summary.name == "Submit Form"
    assert summary.artifact_type == "action"


def test_diagram_entity_not_in_entity_by_path(tmp_path: Path) -> None:
    root = _build_repo(tmp_path / "repo")
    idx = shared_artifact_index(root)
    idx.refresh()
    diagram_path = (root / _DIAGRAM_FILE).resolve()
    # diagram path must NOT appear as a model entity path key
    entity_id_at_path = idx._mem.entity_by_path.get(diagram_path)
    assert entity_id_at_path is None


def test_entities_by_diagram_reverse_index(tmp_path: Path) -> None:
    root = _build_repo(tmp_path / "repo")
    idx = shared_artifact_index(root)
    idx.refresh()
    owned = idx._mem.entities_by_diagram.get(_DIAGRAM_ID, set())
    assert f"{_DIAGRAM_ID}#swimlane/sw-1" in owned
    assert f"{_DIAGRAM_ID}#action/a1" in owned
    assert len(owned) == 5


def test_incremental_update_replaces_diagram_entities(tmp_path: Path) -> None:
    root = _build_repo(tmp_path / "repo")
    idx = shared_artifact_index(root)
    idx.refresh()

    diagram_path = root / _DIAGRAM_FILE
    owned_before = set(idx._mem.entities_by_diagram.get(_DIAGRAM_ID, set()))
    assert len(owned_before) == 5

    # Rewrite diagram with fewer entities (drop second action)
    updated = _ACTIVITY_DIAGRAM_CONTENT.replace(
        "    - id: a2\n      label: Process Request\n      lane_id: sw-2\n",
        "",
    )
    diagram_path.write_text(updated, encoding="utf-8")
    idx.apply_file_changes([diagram_path])

    owned_after = set(idx._mem.entities_by_diagram.get(_DIAGRAM_ID, set()))
    assert f"{_DIAGRAM_ID}#action/a1" in owned_after
    assert f"{_DIAGRAM_ID}#action/a2" not in owned_after
    assert len(owned_after) == 4
