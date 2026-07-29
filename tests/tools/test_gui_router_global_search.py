"""Tests for the GUI global-search endpoint (GET /api/search, connections router).

Regression coverage for two defects in the navigation search dropdown:
- Documents were mislabeled (artifact_type fell back to "connection") and had an empty
  name because the serializer read ``name`` instead of ``title``.
- Connections (relationships, not navigable destinations) appeared as dead results.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.app_bootstrap import install_module_registry
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.connections import router as connections_router

pytest.importorskip("httpx")

DOC_ID = "STD@1000000050.GblDoc.coding-conventions"
SRC_ID = "REQ@1000000050.GblSrc.alpha-requirement"
TGT_ID = "REQ@1000000050.GblTgt.beta-requirement"
_CONN_TOKEN = "zephyrlink"
DIAGRAM_ID = "ACT@1000000050.GblAct.alpha-workflow"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_md(artifact_id: str, name: str) -> str:
    slug = artifact_id.split(".")[-1].replace("-", "_")
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: requirement
name: "{name}"
version: 0.1.0
status: active
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
alias: REQ_{slug}
```
"""


def _connection_md() -> str:
    return f"""\
---
source-entity: {SRC_ID}
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §connections -->

### archimate-association → {TGT_ID}

This {_CONN_TOKEN} relationship couples alpha to beta.
"""


def _doc_md() -> str:
    return f"""\
---
artifact-id: {DOC_ID}
artifact-type: document
doc-type: standard
title: "Coding Conventions"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

# Coding Conventions

These conventions cover {_CONN_TOKEN} naming and style.
"""


def _activity_diagram() -> str:
    return f"""\
---
artifact-id: {DIAGRAM_ID}
artifact-type: diagram
name: "Alpha Workflow"
diagram-type: activity
version: 0.1.0
status: draft
last-updated: '2026-01-01'
diagram-entities:
  action:
    - id: alpha
      label: Alpha Requirement
---
@startuml alpha-workflow
@enduml
"""


@pytest.fixture()
def search_client(tmp_path: Path):
    from starlette.testclient import TestClient

    root = tmp_path / "engagements" / "ENG-GBL" / "architecture-repository"
    _write(root / "model" / "motivation" / "requirement" / f"{SRC_ID}.md", _entity_md(SRC_ID, "Alpha Requirement"))
    _write(root / "model" / "motivation" / "requirement" / f"{TGT_ID}.md", _entity_md(TGT_ID, "Beta Requirement"))
    _write(root / "model" / "motivation" / "requirement" / f"{SRC_ID}.outgoing.md", _connection_md())
    _write(root / "docs" / "standard" / f"{DOC_ID}.md", _doc_md())
    _write(root / "diagram-catalog" / "diagrams" / f"{DIAGRAM_ID}.puml", _activity_diagram())

    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    app = FastAPI()
    install_module_registry(app)
    app.include_router(connections_router)
    return TestClient(app), repo


class TestGlobalSearchDocumentFields:
    def test_document_hit_uses_title_not_empty_name(self, search_client) -> None:
        client, _ = search_client
        hits = client.get("/api/search?q=conventions").json()["hits"]
        doc = next(h for h in hits if h["artifact_id"] == DOC_ID)
        assert doc["record_type"] == "document"
        assert doc["name"] == "Coding Conventions"

    def test_document_hit_type_is_doc_type_not_connection(self, search_client) -> None:
        client, _ = search_client
        hits = client.get("/api/search?q=conventions").json()["hits"]
        doc = next(h for h in hits if h["artifact_id"] == DOC_ID)
        assert doc["artifact_type"] == "standard"


class TestGlobalSearchExcludesConnections:
    def test_no_connection_record_types_returned(self, search_client) -> None:
        client, _ = search_client
        hits = client.get(f"/api/search?q={_CONN_TOKEN}").json()["hits"]
        assert hits, "query should match the document/connection content"
        assert all(h["record_type"] != "connection" for h in hits)

    def test_connection_would_match_when_included(self, search_client) -> None:
        """Sanity check: the connection IS indexed and matchable — exclusion is deliberate."""
        _, repo = search_client
        result = repo.search_artifacts(_CONN_TOKEN, limit=20, include_connections=True)
        assert any(h.record_type == "connection" for h in result.hits)


class TestGlobalSearchEntityPriority:
    def test_diagram_owned_match_does_not_displace_model_entity(self, search_client) -> None:
        client, _ = search_client
        hits = client.get("/api/search?q=Alpha%20Requirement").json()["hits"]
        assert hits[0]["artifact_id"] == SRC_ID
        assert not any("#action/" in hit["artifact_id"] for hit in hits)
