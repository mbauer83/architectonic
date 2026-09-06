"""Internal-type parity across the `scope` branches of `/api/entities` and
`/api/entity-taxonomy`: internal entity types (GAR proxies) are hidden in every
scope — global, engagement, and merged — while regular entities of the same tier
stay listed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.artifacts.query import ArtifactRepository
from src.infrastructure.artifact_index import combined_artifact_index
from src.infrastructure.rest.routers import state as gui_state
from tests.support.api_app import build_api_app
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
#: A reference standing for an *entity*, where the one above stands for a document. Both are
#: hidden the same way; only this one can be served by the entity read.
ENGAGEMENT_ENTITY_GAR_ID = "GAR@1000000502.EntGar.enterprise-guidelines-requirement"


@pytest.fixture()
def client(tmp_path: Path):
    from starlette.testclient import TestClient

    from src.infrastructure.app_bootstrap import install_module_registry
    from src.infrastructure.rest.routers.entities.router import router as entities_router
    from src.infrastructure.rest.routers.entities.search import router as entity_search_router

    engagement = build_engagement_repo(tmp_path)
    enterprise = build_enterprise_repo(tmp_path)
    write_file(
        enterprise / "model" / "common" / GAR_TYPE / f"{ENTERPRISE_GAR_ID}.md",
        gar_md(ENTERPRISE_GAR_ID, "Stray enterprise proxy", global_artifact_id="STD@1.x.d"),
    )
    write_file(
        engagement / "model" / "common" / GAR_TYPE / f"{ENGAGEMENT_ENTITY_GAR_ID}.md",
        gar_md(
            ENGAGEMENT_ENTITY_GAR_ID,
            "Enterprise Guidelines Requirement",
            global_artifact_id=ENTERPRISE_REQ_ID,
        ),
    )
    index = combined_artifact_index(engagement, enterprise)
    index.refresh()
    repo = ArtifactRepository(index)
    gui_state.init_state(repo, engagement, enterprise)
    app = build_api_app(entities_router, entity_search_router)
    install_module_registry(app)
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


class TestReadingOneByIdDoesNotShowAProxy:
    """The list hides references; the detail read served them to anyone holding the URL.

    What that showed was a proxy entity with a description written for nobody — "Engagement-repo
    proxy for promoted document STD@…" — an artifact the model deliberately keeps out of sight,
    presented as if it were the thing a reader had asked for.
    """

    def test_a_reference_serves_the_artifact_it_stands_for(self, client) -> None:
        response = client.get(f"/api/entities/{ENGAGEMENT_ENTITY_GAR_ID}")

        assert response.status_code == 200, response.text
        assert response.json()["artifact_id"] == ENTERPRISE_REQ_ID

    def test_the_proxy_prose_never_reaches_a_reader(self, client) -> None:
        for reference in (ENGAGEMENT_ENTITY_GAR_ID, ENGAGEMENT_GAR_ID, ENTERPRISE_GAR_ID):
            assert "proxy for promoted" not in client.get(f"/api/entities/{reference}").text

    def test_a_reference_to_a_document_names_it_rather_than_rendering_itself(self, client) -> None:
        """The entity read is not a document's route, and serving the proxy in its place is the one
        thing this must not do — that is the page a reader was shown."""
        response = client.get(f"/api/entities/{ENGAGEMENT_GAR_ID}")

        assert response.status_code == 404
        assert "VisDoc" in response.text

    def test_a_reference_to_something_unreadable_names_it_rather_than_rendering_itself(
        self, client
    ) -> None:
        """The stray enterprise proxy points at an artifact no repository here holds. Serving the
        proxy would be the one thing this must not do, so it says which artifact was meant."""
        response = client.get(f"/api/entities/{ENTERPRISE_GAR_ID}")

        assert response.status_code == 404
        assert "STD@1.x.d" in response.text

    def test_an_ordinary_entity_is_unaffected(self, client) -> None:
        response = client.get(f"/api/entities/{REQ_ID}")

        assert response.status_code == 200
        assert response.json()["artifact_id"] == REQ_ID
