"""Tests for the GUI entity_search and admin router endpoints.

entity_search: GET /api/artifact-search, /api/reference-search.
admin: GET /admin/api/server-info.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.admin import router as admin_router
from src.infrastructure.gui.routers.entity_search import _score_reference_hit
from src.infrastructure.gui.routers.entity_search import router as entity_search_router

httpx = pytest.importorskip("httpx")


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


ENT_ID = "REQ@1000000040.EntSch.search-entity"
DIAG_ID = "DIAG@1000000040.DiagSch.search-diagram"
DOC_ID = "ADR@1000000040.DocSch.search-document"


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

Test entity for search.

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


def _diagram_md(artifact_id: str, name: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: diagram
diagram-type: archimate-application
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---
@startuml
component "A" as a
@enduml
"""


def _doc_md(artifact_id: str, title: str) -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: document
doc-type: adr
title: "{title}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

# {title}

Body text.
"""


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-SRCH" / "architecture-repository"
    _write(root / "model" / "motivation" / "requirement" / f"{ENT_ID}.md", _entity_md(ENT_ID, "Search Entity"))
    _write(root / "diagram-catalog" / "diagrams" / f"{DIAG_ID}.md", _diagram_md(DIAG_ID, "Search Diagram"))
    _write(root / "docs" / "adrs" / f"{DOC_ID}.md", _doc_md(DOC_ID, "Search Document"))
    return root


@pytest.fixture()
def sync_client(populated_root: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import (
        build_runtime_catalogs,
        get_module_registry,
        runtime_catalogs_dependency,
    )

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    app = FastAPI()
    catalogs = build_runtime_catalogs(get_module_registry())
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: catalogs
    app.include_router(entity_search_router)
    return TestClient(app)


@pytest.fixture()
def admin_client(populated_root: Path):
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


# ── _score_reference_hit ──────────────────────────────────────────────────────


class TestScoreReferenceHit:
    def test_empty_query_returns_rank_3(self) -> None:
        score, _, _ = _score_reference_hit("My Entity", "REQ@1.AA.my-entity", "")
        assert score == 3

    def test_exact_name_match_returns_rank_0(self) -> None:
        score, _, _ = _score_reference_hit("My Entity", "REQ@1.AA.my-entity", "my entity")
        assert score == 0

    def test_prefix_match_returns_rank_1(self) -> None:
        score, _, _ = _score_reference_hit("My Entity", "REQ@1.AA.my-entity", "my en")
        assert score == 1

    def test_no_match_returns_rank_2(self) -> None:
        score, _, _ = _score_reference_hit("Foo Bar", "REQ@1.AA.foo", "xyz-no-match")
        assert score == 2


# ── GET /api/artifact-search ──────────────────────────────────────────────────


class TestArtifactSearch:
    def test_returns_hits(self, sync_client) -> None:
        r = sync_client.get("/api/artifact-search?q=Search")
        assert r.status_code == 200
        data = r.json()
        assert "hits" in data
        assert "query" in data

    def test_entity_hit_included(self, sync_client) -> None:
        r = sync_client.get("/api/artifact-search?q=Search")
        assert r.status_code == 200
        ids = [h["artifact_id"] for h in r.json()["hits"]]
        assert ENT_ID in ids

    def test_with_limit(self, sync_client) -> None:
        r = sync_client.get("/api/artifact-search?q=Search&limit=5")
        assert r.status_code == 200
        assert len(r.json()["hits"]) <= 5

    def test_with_include_connections(self, sync_client) -> None:
        r = sync_client.get("/api/artifact-search?q=Search&include_connections=true")
        assert r.status_code == 200

    def test_with_include_diagrams_false(self, sync_client) -> None:
        r = sync_client.get("/api/artifact-search?q=Search&include_diagrams=false")
        assert r.status_code == 200

    def test_with_include_documents_false(self, sync_client) -> None:
        r = sync_client.get("/api/artifact-search?q=Search&include_documents=false")
        assert r.status_code == 200

    def test_query_no_match(self, sync_client) -> None:
        r = sync_client.get("/api/artifact-search?q=xyzzy_no_match_123_unique")
        assert r.status_code == 200
        assert isinstance(r.json()["hits"], list)


# ── GET /api/reference-search ─────────────────────────────────────────────────


class TestReferenceSearch:
    def test_all_kinds(self, sync_client) -> None:
        r = sync_client.get("/api/reference-search?q=Search")
        assert r.status_code == 200
        data = r.json()
        assert "hits" in data
        assert "query" in data

    def test_entity_kind_filter(self, sync_client) -> None:
        r = sync_client.get("/api/reference-search?q=Search&kind=entity")
        assert r.status_code == 200
        for h in r.json()["hits"]:
            assert h["record_type"] == "entity"

    def test_diagram_kind_filter(self, sync_client) -> None:
        r = sync_client.get("/api/reference-search?q=Search&kind=diagram")
        assert r.status_code == 200
        for h in r.json()["hits"]:
            assert h["record_type"] == "diagram"

    def test_document_kind_filter(self, sync_client) -> None:
        r = sync_client.get("/api/reference-search?q=Search&kind=document")
        assert r.status_code == 200
        for h in r.json()["hits"]:
            assert h["record_type"] == "document"

    def test_domain_filter(self, sync_client) -> None:
        r = sync_client.get("/api/reference-search?q=&domains=motivation")
        assert r.status_code == 200

    def test_entity_type_filter(self, sync_client) -> None:
        r = sync_client.get("/api/reference-search?q=&entity_types=requirement")
        assert r.status_code == 200

    def test_doc_type_filter(self, sync_client) -> None:
        r = sync_client.get("/api/reference-search?q=Search&doc_types=adr")
        assert r.status_code == 200

    def test_empty_query_returns_all(self, sync_client) -> None:
        r = sync_client.get("/api/reference-search")
        assert r.status_code == 200

    def test_limit_respected(self, sync_client) -> None:
        r = sync_client.get("/api/reference-search?q=&limit=1")
        assert r.status_code == 200
        assert len(r.json()["hits"]) <= 1


# ── admin server-info ─────────────────────────────────────────────────────────


class TestAdminServerInfo:
    def test_returns_server_info(self, admin_client) -> None:
        r = admin_client.get("/admin/api/server-info")
        assert r.status_code == 200
        data = r.json()
        assert "admin_mode" in data
        assert "read_only" in data
        assert data["admin_mode"] is False

    def test_enterprise_root_none_when_not_configured(self, admin_client) -> None:
        r = admin_client.get("/admin/api/server-info")
        assert r.status_code == 200
        assert r.json()["enterprise_root"] is None

    def test_engagement_root_set(self, admin_client, populated_root: Path) -> None:
        r = admin_client.get("/admin/api/server-info")
        assert r.status_code == 200
        assert r.json()["engagement_root"] is not None
