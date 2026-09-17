"""The FastAPI dependencies that hand a request the registry and catalogs installed on its app.

Here, in the REST layer, rather than beside the installers in `app_bootstrap`: that module is what
the diagram types, the write path, the renderers and the tooling import to build a registry, and a
`Request` annotation there made every one of them import the web framework — which lives in the
`gui` dependency group and is absent from an environment that only generates types.
"""

from __future__ import annotations

from fastapi import Request

from src.domain.modules.module_registry import ModuleRegistry
from src.infrastructure.app_bootstrap import RuntimeCatalogs, module_registry_from_app, runtime_catalogs_from_app


def module_registry_dependency(request: Request) -> ModuleRegistry:
    """FastAPI dependency exposing the installed module registry."""
    return module_registry_from_app(request.app)


def runtime_catalogs_dependency(request: Request) -> RuntimeCatalogs:
    """FastAPI dependency exposing the installed RuntimeCatalogs."""
    return runtime_catalogs_from_app(request.app)
