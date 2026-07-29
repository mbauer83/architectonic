"""Regression: FastAPI dependency annotations must resolve at runtime.

``Request`` was imported under ``if TYPE_CHECKING:`` while ``app_bootstrap`` uses
``from __future__ import annotations``, so FastAPI's ``get_type_hints`` raised
``NameError`` and treated ``request`` as a required query parameter. Every endpoint
depending on these resolvers then returned HTTP 422 — breaking the diagram detail
view (/api/diagram-context), the entity connection editor (/api/ontology), and
/api/diagram-types, /api/modules, and more.
"""

from __future__ import annotations

import typing

from src.infrastructure.app_bootstrap import (
    module_registry_dependency,
    runtime_catalogs_dependency,
)


def test_runtime_dependency_request_annotation_resolves() -> None:
    for fn in (runtime_catalogs_dependency, module_registry_dependency):
        hints = typing.get_type_hints(fn)
        assert "request" in hints, f"{fn.__name__} lost its request parameter"
        assert hints["request"].__name__ == "Request", (
            f"{fn.__name__} request annotation did not resolve to fastapi.Request"
        )
