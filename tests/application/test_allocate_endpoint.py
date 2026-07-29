"""WU-0.3: POST /api/identifiers/allocate endpoint tests."""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI

from src.infrastructure.app_bootstrap import install_module_registry
from src.infrastructure.gui.routers.identifiers import router as identifiers_router

_WORKSPACE_ID_RE = re.compile(r"^[A-Z]+@[0-9]+\.[A-Za-z0-9_-]+\..+$")


@pytest.fixture()
def client():
    starlette_tc = pytest.importorskip("starlette.testclient")
    app = FastAPI()
    install_module_registry(app)
    app.include_router(identifiers_router)
    return starlette_tc.TestClient(app)


def test_allocate_classifier_returns_clf_id(client):
    r = client.post(
        "/api/identifiers/allocate",
        json={"diagram_type": "datatype", "entity_type": "classifier", "name_hint": "customer"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "id" in data
    assert data["id"].startswith("CLF@"), f"Expected CLF@ prefix, got {data['id']!r}"
    assert _WORKSPACE_ID_RE.match(data["id"]), f"ID {data['id']!r} does not match grammar"


def test_allocate_without_name_hint(client):
    r = client.post(
        "/api/identifiers/allocate",
        json={"diagram_type": "datatype", "entity_type": "classifier"},
    )
    assert r.status_code == 200
    assert _WORKSPACE_ID_RE.match(r.json()["id"])


def test_allocate_unknown_diagram_type_returns_404(client):
    r = client.post(
        "/api/identifiers/allocate",
        json={"diagram_type": "no-such-type", "entity_type": "classifier"},
    )
    assert r.status_code == 404


def test_allocate_unknown_entity_type_returns_400(client):
    r = client.post(
        "/api/identifiers/allocate",
        json={"diagram_type": "datatype", "entity_type": "no-such-entity"},
    )
    assert r.status_code == 400


def test_allocate_diagram_scoped_entity_returns_400(client):
    """Diagram-scoped entity types must not use this endpoint (no workspace id)."""
    # If datatype has any diagram-scoped types, test one; otherwise skip.
    from src.diagram_types.datatype import module as dt_module
    diagram_scoped = [
        oe.entity_type
        for oe in dt_module.ui_config.diagram_only_types
        if oe.identity_scope != "workspace"
    ]
    if not diagram_scoped:
        pytest.skip("No diagram-scoped entity types to test against")
    r = client.post(
        "/api/identifiers/allocate",
        json={"diagram_type": "datatype", "entity_type": diagram_scoped[0]},
    )
    assert r.status_code == 400


def test_allocate_produces_unique_ids(client):
    ids = set()
    for _ in range(10):
        r = client.post(
            "/api/identifiers/allocate",
            json={"diagram_type": "datatype", "entity_type": "classifier", "name_hint": "x"},
        )
        assert r.status_code == 200
        ids.add(r.json()["id"])
    assert len(ids) == 10, "Endpoint produced duplicate IDs"
