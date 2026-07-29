"""Route introspection helpers for REST-surface tests.

FastAPI 0.139 / Starlette 1.3 changed ``include_router``: included routers are no
longer flattened into ``app.routes`` (or a parent router's ``.routes``). They are
represented by a lazy ``_IncludedRouter`` wrapper (``path is None``), and the
underlying routes are resolved at request time. Walking ``app.routes`` for
``.path``/``.methods`` therefore no longer sees the mounted API routes.

The stable, public contract for "what paths+methods does this surface expose" is
the generated OpenAPI schema. These helpers read paths+methods from ``openapi()``
so the tests are robust to the inclusion mechanism.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _app_for(surface: FastAPI | APIRouter) -> FastAPI:
    if isinstance(surface, FastAPI):
        return surface
    app = FastAPI()
    app.include_router(surface)
    return app


def openapi_paths(surface: FastAPI | APIRouter) -> set[str]:
    """The set of path templates (e.g. ``/api/entity/remove``) the surface serves."""
    return set(_app_for(surface).openapi().get("paths", {}).keys())


def openapi_method_paths(surface: FastAPI | APIRouter) -> set[tuple[str, str]]:
    """The set of ``(METHOD, path)`` pairs the surface serves (methods uppercased)."""
    paths = _app_for(surface).openapi().get("paths", {})
    return {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
    }


def openapi_mutation_routes(surface: FastAPI | APIRouter) -> set[tuple[str, str]]:
    """``(METHOD, path)`` pairs restricted to mutation methods (POST/PUT/PATCH/DELETE)."""
    return {mp for mp in openapi_method_paths(surface) if mp[0] in _MUTATION_METHODS}
