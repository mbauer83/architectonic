"""Regression: the real backend app must mount the module discovery route."""

from __future__ import annotations

from starlette.testclient import TestClient

from src.infrastructure.backend.arch_backend_app import _build_app


def test_backend_app_serves_modules_route() -> None:
    response = TestClient(_build_app()).get("/api/modules")
    assert response.status_code == 200
    names = {entry["name"] for entry in response.json()}
    assert "archimate-4-0" in names
    assert "sysml_v2_min" not in names
