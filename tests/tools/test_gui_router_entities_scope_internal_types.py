"""Internal-type parity across the `scope` branches of `/api/entities` and
`/api/entity-taxonomy`: internal entity types (GAR proxies) are hidden in every
scope — global, engagement, and merged — while regular entities of the same tier
stay listed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from src.application.artifact_query import ArtifactRepository
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.gui.routers import state as gui_state
from tests.support.search_visibility_fixtures import (
    ENTERPRISE_REQ_ID,
    GAR_TYPE,
    REQ_ID,
    build_engagement_repo,
    build_enterprise_repo,
    gar_md,
    write_file,
)

pytest.importorskip("httpx")

ENTERPRISE_GAR_ID = "GAR@1000000501.ScpGar.stray-enterprise-proxy"
ENGAGEMENT_GAR_ID = "GAR@1000000103.VisGar.general-coding-guidelines"


@pytest.fixture()
def client(tmp_path: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.gui.routers.entities import router as entities_router
    from src.infrastructure.gui.routers.entity_search import router as entity_search_router

    engagement = build_engagement_repo(tmp_path)
    enterprise = build_enterprise_repo(tmp_path)
    write_file(
        enterprise / "model" / "common" / GAR_TYPE / f"{ENTERPRISE_GAR_ID}.md",
        gar_md(ENTERPRISE_GAR_ID, "Stray enterprise proxy", global_artifact_id="STD@1.x.d"),
    )
    index = combined_artifact_index(engagement, enterprise)
    index.refresh()
    repo = ArtifactRepository(index)
    gui_state.init_state(repo, engagement, enterprise)
    app = FastAPI()
    install_module_registry(app)
    app.include_router(entities_router)
    app.include_router(entity_search_router)
    return TestClient(app)


def _entity_ids(payload: dict) -> list[str]:
    return [str(item["artifact_id"]) for item in payload["items"]]


def _taxonomy_types(payload: dict) -> set[str]:
    return {t["name"] for d in payload["domains"] for t in d["types"]}


class TestEntitiesListScopes:
    def test_global_scope_hides_internal_types(self, client) -> None:
        ids = _entity_ids(client.get("/api/entities?scope=global").json())
        assert ENTERPRISE_REQ_ID in ids
        assert ENTERPRISE_GAR_ID not in ids

    def test_engagement_scope_hides_internal_types(self, client) -> None:
        ids = _entity_ids(client.get("/api/entities?scope=engagement").json())
        assert REQ_ID in ids
        assert ENGAGEMENT_GAR_ID not in ids

    def test_merged_scope_hides_internal_types_from_both_tiers(self, client) -> None:
        ids = _entity_ids(client.get("/api/entities").json())
        assert REQ_ID in ids
        assert ENTERPRISE_REQ_ID in ids
        assert ENGAGEMENT_GAR_ID not in ids
        assert ENTERPRISE_GAR_ID not in ids

    def test_global_total_excludes_hidden_rows(self, client) -> None:
        payload = client.get("/api/entities?scope=global").json()
        assert payload["total"] == len(payload["items"])
        assert payload["total"] == 1


class TestEntityTaxonomyScopes:
    def test_global_scope_hides_internal_types(self, client) -> None:
        types = _taxonomy_types(client.get("/api/entity-taxonomy?scope=global").json())
        assert "requirement" in types
        assert GAR_TYPE not in types

    def test_engagement_scope_hides_internal_types(self, client) -> None:
        types = _taxonomy_types(client.get("/api/entity-taxonomy?scope=engagement").json())
        assert "requirement" in types
        assert GAR_TYPE not in types

    def test_merged_scope_hides_internal_types(self, client) -> None:
        types = _taxonomy_types(client.get("/api/entity-taxonomy").json())
        assert "requirement" in types
        assert GAR_TYPE not in types
