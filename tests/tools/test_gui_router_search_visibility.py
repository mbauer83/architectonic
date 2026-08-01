"""GAR visibility on the REST search surfaces.

`/api/search` and `/api/artifact-search` flow through the repository search policy
(the backend composition root injects the internal-type exclusion set); this file
exercises them with a policy-bearing repository and pins the already-safe
`/api/reference-search` and `/api/entity-display-search` filters.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from tests.support.api_app import build_api_app
from tests.support.search_visibility_fixtures import (
    EXCLUDED_TYPES,
    GAR_ID,
    QUERY,
    REQ_ID,
    build_engagement_repo,
)

pytest.importorskip("httpx")


@pytest.fixture()
def client(tmp_path: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import (
        build_runtime_catalogs,
        get_module_registry,
        runtime_catalogs_dependency,
    )
    from src.infrastructure.rest.routers.connections.router import router as connections_router
    from src.infrastructure.rest.routers.diagrams.router import router as diagrams_router
    from src.infrastructure.rest.routers.entities.search import router as entity_search_router

    root = build_engagement_repo(tmp_path)
    repo = ArtifactRepository(shared_artifact_index([root]), excluded_entity_types=EXCLUDED_TYPES)
    gui_state.init_state(repo, root, None)
    app = build_api_app(connections_router, entity_search_router, diagrams_router)
    catalogs = build_runtime_catalogs(get_module_registry())
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: catalogs
    return TestClient(app)


def _ids(hits: list[dict]) -> list[str]:
    return [str(h["artifact_id"]) for h in hits]


class TestGlobalSearchEndpoint:
    def test_gar_absent_real_entity_present(self, client) -> None:
        hits = client.get(f"/api/search?q={QUERY}").json()["hits"]
        assert REQ_ID in _ids(hits)
        assert GAR_ID not in _ids(hits)


class TestArtifactSearchEndpoint:
    def test_gar_absent_real_entity_present(self, client) -> None:
        hits = client.get(f"/api/artifact-search?q={QUERY}").json()["hits"]
        assert REQ_ID in _ids(hits)
        assert GAR_ID not in _ids(hits)


class TestReferenceSearchStaysSafe:
    def test_gar_absent_real_entity_present(self, client) -> None:
        hits = client.get(f"/api/reference-search?q={QUERY}&kind=entity").json()["hits"]
        assert REQ_ID in _ids(hits)
        assert GAR_ID not in _ids(hits)


class TestEntityDisplaySearchStaysSafe:
    def test_gar_absent_real_entity_present(self, client) -> None:
        items = client.get(f"/api/entity-display-search?q={QUERY}").json()["items"]
        ids = [str(item["artifact_id"]) for item in items]
        assert REQ_ID in ids
        assert GAR_ID not in ids
