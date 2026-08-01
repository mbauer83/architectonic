"""GET /api/assurance/edge-catalog transport contract: serves the loaded
module's catalog when the assurance capability is configured (module
registered), 404s when it is not, and never requires the store to be unlocked
— it carries module configuration, not store content."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from src.application.assurance.edge_catalog import build_edge_catalog
from src.domain.modules.module_registry import ModuleRegistry
from src.infrastructure.app_bootstrap import assurance_ontology_module
from tests.support.api_app import build_api_app


def _client() -> TestClient:
    from src.infrastructure.rest.routers.assurance import router

    # `build_api_app`, not a bare `FastAPI()`: without the error contracts installed a raised
    # `ApiError` becomes a 500 and the test asserts a shape no client receives.
    app = build_api_app(router)
    return TestClient(app, raise_server_exceptions=False)


def test_configured_catalog_equals_the_module_representation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infrastructure.rest.routers.assurance as routes

    registry = ModuleRegistry()
    module = assurance_ontology_module()
    registry.register_ontology(module)  # type: ignore[arg-type]
    monkeypatch.setattr(routes, "get_module_registry", lambda: registry)

    resp = _client().get("/api/assurance/edge-catalog")
    assert resp.status_code == 200
    assert resp.json() == build_edge_catalog(module)


def test_unconfigured_capability_is_a_404(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.infrastructure.rest.routers.assurance as routes

    monkeypatch.setattr(routes, "get_module_registry", lambda: ModuleRegistry())
    resp = _client().get("/api/assurance/edge-catalog")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    # `not_configured`, not `conflict`: nothing the caller sends can fix an unconfigured module, so
    # reporting it as a request problem would send them to correct a correct request.
    assert detail["code"] == "not_configured"
    assert detail["details"]["capability"] == "assurance"


def test_catalog_needs_no_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    """No assurance context is touched at all — a locked or absent store cannot
    influence the catalog (it would raise if the endpoint tried)."""
    import src.infrastructure.rest.routers.assurance as routes
    from src.infrastructure.mcp.assurance_mcp import context as ctx_module

    registry = ModuleRegistry()
    registry.register_ontology(assurance_ontology_module())  # type: ignore[arg-type]
    monkeypatch.setattr(routes, "get_module_registry", lambda: registry)

    def _boom() -> object:
        raise AssertionError("edge-catalog must not build the assurance context")

    monkeypatch.setattr(ctx_module, "get_assurance_context", _boom)
    resp = _client().get("/api/assurance/edge-catalog")
    assert resp.status_code == 200
