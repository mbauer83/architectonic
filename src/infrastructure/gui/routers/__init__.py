"""GUI HTTP routers."""

from __future__ import annotations


def include_default_routers(app):  # type: ignore[no-untyped-def]
    from src.infrastructure.gui.routers.diagram_types import router as diagram_types_router
    from src.infrastructure.gui.routers.modules import router as modules_router

    app.include_router(diagram_types_router)
    app.include_router(modules_router)
