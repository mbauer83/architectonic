"""Registry ⇔ manifest equality for the REST mutation surface.

Every POST/PUT/PATCH/DELETE route on the real backend app is either a manifested
architecture-repository mutator, an explicitly classified non-mutating route, or
an assurance-store route (own gating, excluded by prefix); both directions of
the equality hold, and the request builder is exercised per intent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.mutation_authorization import (
    DiscardWrite,
    MutationRequest,
    PromotionWrite,
    RepositoryWrite,
)
from src.infrastructure.gui.routers.rest_mutation_manifest import (
    ASSURANCE_ROUTE_PREFIX,
    NON_MUTATING_REST_ROUTES,
    REST_MUTATION_MANIFEST,
    build_rest_request,
)
from tests.support.route_introspection import openapi_mutation_routes


def _app_mutation_routes() -> set[tuple[str, str]]:
    """Walk the SAME router set the backend app assembles (arch_backend_app)."""
    from fastapi import FastAPI

    from src.infrastructure.gui.routers.admin import router as admin_router
    from src.infrastructure.gui.routers.assurance import router as assurance_router
    from src.infrastructure.gui.routers.authoring_guidance import router as authoring_guidance_router
    from src.infrastructure.gui.routers.connections import router as connections_router
    from src.infrastructure.gui.routers.diagram_types import router as diagram_types_router
    from src.infrastructure.gui.routers.diagrams import router as diagrams_router
    from src.infrastructure.gui.routers.documents import router as documents_router
    from src.infrastructure.gui.routers.entities import router as entities_router
    from src.infrastructure.gui.routers.entity_search import router as entity_search_router
    from src.infrastructure.gui.routers.events import router as events_router
    from src.infrastructure.gui.routers.groups import router as groups_router
    from src.infrastructure.gui.routers.identifiers import router as identifiers_router
    from src.infrastructure.gui.routers.modules import router as modules_router
    from src.infrastructure.gui.routers.promote import router as promote_router
    from src.infrastructure.gui.routers.sync import router as sync_router
    from src.infrastructure.gui.routers.viewpoint_authoring import router as viewpoint_authoring_router
    from src.infrastructure.gui.routers.viewpoints import router as viewpoints_router

    app = FastAPI()
    for router in (
        entities_router, entity_search_router, connections_router, diagram_types_router,
        diagrams_router, documents_router, groups_router, identifiers_router, modules_router, promote_router,
        sync_router, admin_router, events_router, assurance_router, authoring_guidance_router,
        viewpoints_router, viewpoint_authoring_router,
    ):
        app.include_router(router)
    return openapi_mutation_routes(app)


class TestRestRegistryManifestEquality:
    def test_every_mutation_route_is_classified_and_every_row_registered(self) -> None:
        app_routes = {
            route for route in _app_mutation_routes() if not route[1].startswith(ASSURANCE_ROUTE_PREFIX)
        }
        classified = set(REST_MUTATION_MANIFEST) | NON_MUTATING_REST_ROUTES
        assert app_routes == classified

    def test_manifest_and_non_mutating_sets_are_disjoint(self) -> None:
        assert not set(REST_MUTATION_MANIFEST) & NON_MUTATING_REST_ROUTES


class TestBuildRestRequest:
    @pytest.fixture()
    def roots(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
        engagement = tmp_path / "engagements" / "ENG-RRM" / "architecture-repository"
        enterprise = tmp_path / "enterprise-repository"
        engagement.mkdir(parents=True)
        enterprise.mkdir(parents=True)
        monkeypatch.setattr("src.infrastructure.gui.routers.state.maybe_engagement_root", lambda: engagement)
        monkeypatch.setattr("src.infrastructure.gui.routers.state.maybe_enterprise_root", lambda: enterprise)
        monkeypatch.setattr(
            "src.infrastructure.gui.routers.state.get_both_roots", lambda: (engagement, enterprise)
        )
        return engagement, enterprise

    def test_every_manifest_row_builds_its_declared_intent(self, roots) -> None:
        for route, intent in REST_MUTATION_MANIFEST.items():
            request = build_rest_request(route)
            assert isinstance(request, MutationRequest), route
            assert request.intent == intent, route

    def test_engagement_routes_target_the_engagement_root(self, roots) -> None:
        engagement, _ = roots
        request = build_rest_request(("POST", "/api/entity"))
        assert request.target == RepositoryWrite(engagement)

    def test_promotion_route_targets_both_roots(self, roots) -> None:
        engagement, enterprise = roots
        request = build_rest_request(("POST", "/api/promote/execute"))
        assert request.target == PromotionWrite(engagement, enterprise)

    def test_withdraw_route_distinguishes_pending_remote(self, roots, monkeypatch: pytest.MonkeyPatch) -> None:
        _, enterprise = roots
        request = build_rest_request(("POST", "/api/sync/enterprise/withdraw"))
        assert request.target == DiscardWrite(enterprise, pending_remote=False)

        class _Pending:
            def is_pending(self) -> bool:
                return True

        monkeypatch.setattr("src.infrastructure.git.enterprise_sync_state.load", lambda root: _Pending())
        assert build_rest_request(("POST", "/api/sync/enterprise/withdraw")).target == DiscardWrite(
            enterprise, pending_remote=True
        )

    def test_unmanifested_route_cannot_execute(self, roots) -> None:
        with pytest.raises(LookupError, match="classify the route"):
            build_rest_request(("POST", "/api/not-a-route"))
