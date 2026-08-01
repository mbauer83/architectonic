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

from tests.support.api_app import build_api_app

#: The modelling surface, by module path under `rest.routers`. Each surface with more than one
#: module is a package now, so the public router lives at `<surface>.router` and the module path is
#: what names it — a bare surface name would import the package and find no routes.
_IN_SCOPE_ROUTER_MODULES = [
    "entities.router",
    "entities.search",
    "connections.router",
    "diagrams.router",
    "documents",
    "groups",
    "identifiers",
    "modules",
    "diagrams.types",
    "authoring_guidance",
    "viewpoints.router",
    "viewpoints.authoring",
]

# Endpoints that legitimately return a media body (image/SVG/file), not JSON — a JSON
# response_model does not apply; they still carry a tag + summary.
_MEDIA_PATHS = {
    "/api/diagram-images/{filename}",
    "/api/diagrams/{artifact_id}/svg",
    "/api/diagrams/{artifact_id}/download",
}

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

    app = build_api_app(
        *(
            importlib.import_module(f"src.infrastructure.rest.routers.{name}").router
            for name in _IN_SCOPE_ROUTER_MODULES
        )
    )
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


def test_every_operation_documents_its_success_body(spec: dict) -> None:
    """Every operation says what it answers with — including saying that it answers with nothing.

    A ``204`` satisfies this: it is a declared success status that may not carry a body, which is a
    contract rather than an omission. A ``201`` must document its body like a ``200``, because a
    create answers with the resource it made.
    """
    missing = [
        f"{method.upper()} {path}"
        for path, method, op in _operations(spec)
        if path not in _MEDIA_PATHS
        and "204" not in op.get("responses", {})
        and not any(
            "content" in op.get("responses", {}).get(status, {}) for status in ("200", "201")
        )
    ]
    assert missing == [], f"operations without a documented success body: {missing}"


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
