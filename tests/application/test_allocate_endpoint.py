"""WU-0.3: POST /api/identifiers/allocate endpoint tests."""

from __future__ import annotations

import re

import pytest

from src.infrastructure.app_bootstrap import install_module_registry
from src.infrastructure.rest.routers.identifiers import router as identifiers_router
from tests.support.api_app import build_api_app

_WORKSPACE_ID_RE = re.compile(r"^[A-Z]+@[0-9]+\.[A-Za-z0-9_-]+\..+$")


@pytest.fixture()
def client():
    starlette_tc = pytest.importorskip("starlette.testclient")
    app = build_api_app(identifiers_router)
    install_module_registry(app)
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


def test_allocate_refuses_an_entity_type_that_is_not_workspace_scoped() -> None:
    """Only a workspace-scoped type has an id this endpoint can allocate.

    Stated against a stubbed catalogue rather than against the shipped one. It used to look for a
    diagram-scoped type among the datatype module's own, and skip when there was none — and there has
    never been one: both of that module's diagram-owned types are workspace-scoped, so the assertion
    below had never executed. A test whose subject is a property of the *rule* must not be conditional
    on today's content, which is the same reason this repository forbids asserting exact counts
    against the live model.
    """
    starlette_tc = pytest.importorskip("starlette.testclient")
    from src.infrastructure.app_bootstrap import runtime_catalogs_dependency

    class _Entry:
        entity_type = "scoped-thing"
        identity_scope = "diagram"
        id_prefix = "SCT"

    class _Module:
        class ui_config:  # noqa: N801
            diagram_only_types = (_Entry(),)

    class _DiagramTypes:
        def find_diagram_type(self, name: str) -> object | None:
            return _Module() if name == "stub" else None

    class _Catalogs:
        diagram_types = _DiagramTypes()

    app = build_api_app(identifiers_router)
    install_module_registry(app)
    app.dependency_overrides[runtime_catalogs_dependency] = lambda: _Catalogs()

    response = starlette_tc.TestClient(app).post(
        "/api/identifiers/allocate",
        json={"diagram_type": "stub", "entity_type": "scoped-thing"},
    )

    assert response.status_code == 400
    assert "identity_scope" in response.text


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
