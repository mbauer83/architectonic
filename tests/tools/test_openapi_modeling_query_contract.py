"""WU-OA4 (D5): the modeling & querying REST surface's OpenAPI fidelity, locked.

Every in-scope operation must carry a tag, a summary, and a documented 200 body (a
``response_model`` → a real schema, or an explicit media response). Write operations must
declare the gate/authorization error statuses. A new modeling endpoint that skips any of
this fails here — the fidelity cannot silently regress.

Scope is the modeling/query routers (PLAN §2); assurance/security, promotion, sync, admin,
and events are a deferred second pass and are NOT asserted here.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI

_IN_SCOPE_ROUTER_MODULES = [
    "entities",
    "entity_search",
    "connections",
    "diagrams",
    "documents",
    "groups",
    "identifiers",
    "modules",
    "diagram_types",
    "authoring_guidance",
    "viewpoints",
    "viewpoint_authoring",
]

# Endpoints that legitimately return a media body (image/SVG/file), not JSON — a JSON
# response_model does not apply; they still carry a tag + summary.
_MEDIA_PATHS = {"/api/diagram-image/{filename}", "/api/diagram-svg", "/api/diagram-download"}

# Write operations declare the mutation-gate / authorization error contract.
_WRITE_STATUSES = {"400", "403", "409", "423"}
_WRITE_METHODS = {"post", "put", "patch", "delete"}
# Reads-via-POST that execute a query rather than mutate — no write-gate statuses expected.
_READ_VIA_POST = {
    "/api/viewpoints/execute",
    "/api/viewpoints/export-csv",
    "/api/viewpoints/execute-projection",
    "/api/viewpoints/execute-diagram",
    "/api/viewpoints/summarize",
    "/api/viewpoints/export-render",
    "/api/identifiers/allocate",
}


@pytest.fixture(scope="module")
def spec() -> dict:
    from src.infrastructure.app_bootstrap import install_module_registry

    app = FastAPI()
    for name in _IN_SCOPE_ROUTER_MODULES:
        app.include_router(importlib.import_module(f"src.infrastructure.gui.routers.{name}").router)
    install_module_registry(app)
    return app.openapi()


def _operations(spec: dict):
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            yield path, method, op


def test_every_operation_has_a_tag_and_summary(spec: dict) -> None:
    missing = [
        f"{method.upper()} {path}"
        for path, method, op in _operations(spec)
        if not op.get("tags") or not op.get("summary")
    ]
    assert missing == [], f"operations missing a tag or summary: {missing}"


def test_every_operation_documents_its_200_body(spec: dict) -> None:
    missing = [
        f"{method.upper()} {path}"
        for path, method, op in _operations(spec)
        if path not in _MEDIA_PATHS and "content" not in op.get("responses", {}).get("200", {})
    ]
    assert missing == [], f"operations without a documented 200 body: {missing}"


def test_write_operations_declare_the_error_contract(spec: dict) -> None:
    missing = []
    for path, method, op in _operations(spec):
        if method not in _WRITE_METHODS or path in _READ_VIA_POST:
            continue
        declared = set(op.get("responses", {}))
        if not _WRITE_STATUSES <= declared:
            missing.append(f"{method.upper()} {path}: has {sorted(declared & _WRITE_STATUSES)}")
    assert missing == [], f"write operations missing gate/authorization statuses: {missing}"


def test_id_lookup_reads_declare_404(spec: dict) -> None:
    # A GET that takes an id/slug path parameter can 404; it must say so.
    missing = [
        f"GET {path}"
        for path, method, op in _operations(spec)
        if method == "get" and ("{id}" in path or "{slug}" in path or "{artifact_id}" in path)
        and "404" not in op.get("responses", {})
    ]
    assert missing == [], f"id-lookup reads missing a documented 404: {missing}"
