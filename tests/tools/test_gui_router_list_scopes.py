"""Tier (scope) facets on the documents and diagrams list endpoints: one artifact
per tier, exact totals filtered BEFORE pagination, required `is_global` badge
values, and tier+type / tier+group filter combinations.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from tests.support.search_visibility_fixtures import write_file

pytest.importorskip("httpx")

ENG_DOC_ID = "ADR@1000000801.LscDe.engagement-decision"
ENT_DOC_ID = "STD@1000000802.LscDn.enterprise-standard"
ENG_DIA_ID = "ARC@1000000803.LscGe.engagement-diagram"
ENT_DIA_ID = "ARC@1000000804.LscGn.enterprise-diagram"


def _doc_md(artifact_id: str, doc_type: str, title: str) -> str:
    return (
        "---\n"
        f"artifact-id: {artifact_id}\n"
        "artifact-type: document\n"
        f"doc-type: {doc_type}\n"
        f"title: {title}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n\n"
        f"# {title}\n"
    )


def _diagram_md(artifact_id: str, name: str) -> str:
    return (
        "---\n"
        f"artifact-id: {artifact_id}\n"
        "artifact-type: diagram\n"
        "diagram-type: archimate-motivation\n"
        f"name: {name}\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "last-updated: '2026-01-01'\n"
        "---\n"
        "@startuml\n@enduml\n"
    )


@pytest.fixture()
def client(tmp_path: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.gui.routers.diagrams import router as diagrams_router
    from src.infrastructure.gui.routers.documents import router as documents_router

    engagement = tmp_path / "engagements" / "ENG-LSC" / "architecture-repository"
    enterprise = tmp_path / "enterprise-repository"
    write_file(
        engagement / "docs" / "adr" / "eng-group" / f"{ENG_DOC_ID}.md",
        _doc_md(ENG_DOC_ID, "adr", "Engagement Decision"),
    )
    write_file(
        enterprise / "docs" / "standard" / "ent-group" / f"{ENT_DOC_ID}.md",
        _doc_md(ENT_DOC_ID, "standard", "Enterprise Standard"),
    )
    write_file(
        engagement / "diagram-catalog" / "diagrams" / "eng-views" / f"{ENG_DIA_ID}.puml",
        _diagram_md(ENG_DIA_ID, "Engagement Diagram"),
    )
    write_file(
        enterprise / "diagram-catalog" / "diagrams" / "ent-views" / f"{ENT_DIA_ID}.puml",
        _diagram_md(ENT_DIA_ID, "Enterprise Diagram"),
    )
    index = combined_artifact_index(engagement, enterprise)
    index.refresh()
    repo = ArtifactRepository(index)
    gui_state.init_state(repo, engagement, enterprise)
    app = FastAPI()
    app.include_router(documents_router)
    app.include_router(diagrams_router)
    return TestClient(app)


class TestDocumentScopes:
    def test_all_lists_both_tiers_with_required_badges(self, client) -> None:
        payload = client.get("/api/documents").json()
        assert payload["total"] == 2
        badge_by_id = {item["artifact_id"]: item["is_global"] for item in payload["items"]}
        assert badge_by_id == {ENG_DOC_ID: False, ENT_DOC_ID: True}

    def test_global_scope_exact_total(self, client) -> None:
        payload = client.get("/api/documents?scope=global").json()
        assert payload["total"] == 1
        assert [item["artifact_id"] for item in payload["items"]] == [ENT_DOC_ID]

    def test_engagement_scope_exact_total(self, client) -> None:
        payload = client.get("/api/documents?scope=engagement").json()
        assert payload["total"] == 1
        assert [item["artifact_id"] for item in payload["items"]] == [ENG_DOC_ID]

    def test_filter_happens_before_pagination(self, client) -> None:
        """With limit=1 the enterprise document still fills the page — hidden-tier
        rows never consume the page or the total."""
        payload = client.get("/api/documents?scope=global&limit=1").json()
        assert payload["total"] == 1
        assert [item["artifact_id"] for item in payload["items"]] == [ENT_DOC_ID]

    def test_scope_combines_with_doc_type(self, client) -> None:
        assert client.get("/api/documents?scope=global&doc_type=standard").json()["total"] == 1
        assert client.get("/api/documents?scope=global&doc_type=adr").json()["total"] == 0

    def test_scope_combines_with_group(self, client) -> None:
        assert client.get("/api/documents?scope=engagement&group=eng-group").json()["total"] == 1
        assert client.get("/api/documents?scope=global&group=eng-group").json()["total"] == 0


class TestDiagramScopes:
    def test_all_lists_both_tiers_with_required_badges(self, client) -> None:
        payload = client.get("/api/diagrams").json()
        assert payload["total"] == 2
        badge_by_id = {item["artifact_id"]: item["is_global"] for item in payload["items"]}
        assert badge_by_id == {ENG_DIA_ID: False, ENT_DIA_ID: True}

    def test_global_scope_exact_total(self, client) -> None:
        payload = client.get("/api/diagrams?scope=global").json()
        assert payload["total"] == 1
        assert [item["artifact_id"] for item in payload["items"]] == [ENT_DIA_ID]

    def test_engagement_scope_exact_total(self, client) -> None:
        payload = client.get("/api/diagrams?scope=engagement").json()
        assert payload["total"] == 1
        assert [item["artifact_id"] for item in payload["items"]] == [ENG_DIA_ID]

    def test_scope_combines_with_diagram_type(self, client) -> None:
        assert client.get("/api/diagrams?scope=global&diagram_type=archimate-motivation").json()["total"] == 1
        assert client.get("/api/diagrams?scope=global&diagram_type=matrix").json()["total"] == 0

    def test_scope_combines_with_group(self, client) -> None:
        assert client.get("/api/diagrams?scope=global&group=ent-views").json()["total"] == 1
        assert client.get("/api/diagrams?scope=engagement&group=ent-views").json()["total"] == 0
