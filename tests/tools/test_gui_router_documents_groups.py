"""Tests for GUI documents and groups routers.

Covers: GET /api/document-types, /api/document-schemata, /api/documents,
/api/document (found + not-found); POST /api/document (dry_run);
GET /api/groups (all axes + filtered).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from src.infrastructure.gui.routers.documents import router as documents_router
from src.infrastructure.gui.routers.groups import router as groups_router

httpx = pytest.importorskip("httpx")


# ── helpers ───────────────────────────────────────────────────────────────────

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


DOC_ID = "ADR@1000000030.DocDTst.test-document"

_ADR_SCHEMA = """\
{
  "abbreviation": "ADR",
  "name": "Architecture Decision Record",
  "subdirectory": "adr",
  "frontmatter_schema": {
    "type": "object",
    "required": ["title", "status"],
    "properties": {
      "title": {"type": "string"},
      "status": {"type": "string"}
    }
  },
  "required_sections": ["Context", "Decision", "Consequences"]
}
"""

_STANDARD_SCHEMA = """\
{
  "abbreviation": "STD",
  "name": "Standard",
  "subdirectory": "standards",
  "frontmatter_schema": {
    "type": "object",
    "required": ["title", "status"],
    "properties": {
      "title": {"type": "string"},
      "status": {"type": "string"}
    }
  },
  "sections": [
    {"name": "Overview"},
    {
      "name": "Decision",
      "required_entity_type_connections": ["requirement"],
      "suggested_entity_type_connections": ["@all"]
    }
  ]
}
"""


def _doc_md(artifact_id: str, title: str, doc_type: str = "adr") -> str:
    return f"""\
---
artifact-id: {artifact_id}
artifact-type: document
doc-type: {doc_type}
title: "{title}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

# {title}

Document body text here.
"""


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def populated_root(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-DOC" / "architecture-repository"
    _write(root / "docs" / "adrs" / f"{DOC_ID}.md", _doc_md(DOC_ID, "Test Document"))
    _write(root / ".arch-repo" / "documents" / "adr.json", _ADR_SCHEMA)
    _write(root / ".arch-repo" / "documents" / "standard.json", _STANDARD_SCHEMA)
    return root


@pytest.fixture()
def doc_client(populated_root: Path):
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    app = FastAPI()
    app.include_router(documents_router)
    return TestClient(app)


@pytest.fixture()
def group_client(populated_root: Path):
    from starlette.testclient import TestClient

    repo = ArtifactRepository(shared_artifact_index([populated_root]))
    gui_state.init_state(repo, populated_root, None)
    app = FastAPI()
    app.include_router(groups_router)
    return TestClient(app)


# ── document-types ────────────────────────────────────────────────────────────


class TestDocumentTypes:
    def test_returns_list(self, doc_client) -> None:
        r = doc_client.get("/api/document-types")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_canonical_sections_exposed_with_per_section_entity_rules(self, doc_client) -> None:
        r = doc_client.get("/api/document-types")
        assert r.status_code == 200
        by_type = {item["doc_type"]: item for item in r.json()}
        standard = by_type["standard"]
        assert standard["sections"] == [
            {"name": "Overview"},
            {
                "name": "Decision",
                "required_entity_type_connections": ["requirement"],
                "suggested_entity_type_connections": ["@all"],
            },
        ]

    def test_legacy_schema_normalizes_to_sections_without_entity_rules(self, doc_client) -> None:
        r = doc_client.get("/api/document-types")
        assert r.status_code == 200
        by_type = {item["doc_type"]: item for item in r.json()}
        adr = by_type["adr"]
        assert adr["sections"] == [
            {"name": "Context"},
            {"name": "Decision"},
            {"name": "Consequences"},
        ]

    def test_schemata_endpoint(self, doc_client) -> None:
        r = doc_client.get("/api/document-schemata")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)


# ── list documents ────────────────────────────────────────────────────────────


class TestListDocuments:
    def test_returns_total_and_items(self, doc_client) -> None:
        r = doc_client.get("/api/documents")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "items" in data

    def test_lists_created_document(self, doc_client) -> None:
        r = doc_client.get("/api/documents")
        assert r.status_code == 200
        ids = [d["artifact_id"] for d in r.json()["items"]]
        assert DOC_ID in ids

    def test_filter_by_doc_type(self, doc_client) -> None:
        r = doc_client.get("/api/documents?doc_type=adr")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_filter_by_status(self, doc_client) -> None:
        r = doc_client.get("/api/documents?status=draft")
        assert r.status_code == 200

    def test_pagination(self, doc_client) -> None:
        r = doc_client.get("/api/documents?limit=5&offset=0")
        assert r.status_code == 200


# ── read document ─────────────────────────────────────────────────────────────


class TestReadDocument:
    def test_found(self, doc_client) -> None:
        r = doc_client.get(f"/api/document?id={DOC_ID}")
        assert r.status_code == 200
        data = r.json()
        assert data["artifact_id"] == DOC_ID

    def test_not_found_returns_404(self, doc_client) -> None:
        r = doc_client.get("/api/document?id=ADR@9.ZZZ.no-such")
        assert r.status_code == 404


# ── create document ───────────────────────────────────────────────────────────


class TestCreateDocument:
    def test_dry_run_returns_result(self, doc_client) -> None:
        payload = {
            "doc_type": "adr",
            "title": "Test ADR Title",
            "body": "## Context\n\nTest content.",
            "dry_run": True,
        }
        r = doc_client.post("/api/document", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "wrote" in data
        assert data["wrote"] is False

    def test_with_keywords(self, doc_client) -> None:
        payload = {
            "doc_type": "adr",
            "title": "ADR With Keywords",
            "keywords": ["arch", "security"],
            "dry_run": True,
        }
        r = doc_client.post("/api/document", json=payload)
        assert r.status_code == 200


# ── groups ────────────────────────────────────────────────────────────────────


class TestListGroups:
    def test_returns_all_axes(self, group_client) -> None:
        r = group_client.get("/api/groups")
        assert r.status_code == 200
        data = r.json()
        assert "model-projects" in data
        assert "diagram-collections" in data
        assert "document-collections" in data

    def test_filter_model_project(self, group_client) -> None:
        r = group_client.get("/api/groups?kind=model-project")
        assert r.status_code == 200
        data = r.json()
        assert "model-projects" in data
        assert "diagram-collections" not in data

    def test_filter_diagram_collection(self, group_client) -> None:
        r = group_client.get("/api/groups?kind=diagram-collection")
        assert r.status_code == 200
        data = r.json()
        assert "diagram-collections" in data

    def test_filter_document_collection(self, group_client) -> None:
        r = group_client.get("/api/groups?kind=document-collection")
        assert r.status_code == 200
        data = r.json()
        assert "document-collections" in data


# ── group member counts ───────────────────────────────────────────────────────


_GOAL_MD = """\
---
artifact-id: {artifact_id}
artifact-type: goal
name: "{name}"
version: 0.1.0
status: draft
last-updated: '2026-01-01'
---

<!-- §content -->
"""


@pytest.fixture()
def counted_client(tmp_path: Path):
    """Two named projects with 2 and 1 entities plus one uncategorized entity — the sidebar
    regression showed 0 for every group that wasn't the active list filter, because counts were
    derived client-side from the loaded (group-filtered) page instead of the whole catalog."""
    from starlette.testclient import TestClient

    root = tmp_path / "engagements" / "ENG-GRP" / "architecture-repository"
    _write(root / ".arch-repo" / "groups.yaml",
           "model-projects:\n"
           "  - slug: alpha\n"
           "    id: GRP@1.alpha\n"
           "    name: Alpha\n"
           "  - slug: beta\n"
           "    id: GRP@2.beta\n"
           "    name: Beta\n")
    for slug, ids in {"alpha": ["GOL@1.aa.g1", "GOL@1.ab.g2"], "beta": ["GOL@1.ba.g3"]}.items():
        for artifact_id in ids:
            _write(root / "projects" / slug / "model" / "motivation" / "goal" / f"{artifact_id}.md",
                   _GOAL_MD.format(artifact_id=artifact_id, name=artifact_id))
    _write(root / "model" / "motivation" / "goal" / "GOL@1.un.g4.md",
           _GOAL_MD.format(artifact_id="GOL@1.un.g4", name="Ungrouped"))

    repo = ArtifactRepository(shared_artifact_index([root]))
    gui_state.init_state(repo, root, None)
    app = FastAPI()
    app.include_router(groups_router)
    return TestClient(app)


class TestGroupMemberCounts:
    def test_model_project_counts_reflect_the_whole_catalog(self, counted_client) -> None:
        data = counted_client.get("/api/groups?kind=model-project").json()
        counts = {e["slug"]: e["member_count"] for e in data["model-projects"]}
        assert counts["alpha"] == 2
        assert counts["beta"] == 1
        assert counts["uncategorized"] == 1

    def test_every_axis_entry_carries_a_member_count(self, counted_client) -> None:
        data = counted_client.get("/api/groups").json()
        for axis_entries in data.values():
            for entry in axis_entries:
                assert isinstance(entry["member_count"], int)
                assert entry["member_count"] >= 0
