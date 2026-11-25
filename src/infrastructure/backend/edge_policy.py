"""The layers every request passes before the application sees it, installed in their one order.

Starlette runs the middleware added last first, so the order here is outermost last:

1. `HostGuard` refuses a request addressed to a name this backend does not serve, before any other
   layer — the MCP mounts and the GUI's files included (DNS rebinding).
2. `SecurityHeaders` is outside even that, so every response carries the content policy, the guard's
   refusal too.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.infrastructure.backend.host_guard import HostGuard
from src.infrastructure.backend.security_headers import SecurityHeaders


def install_edge_policy(app: FastAPI, *, documentation_pages: frozenset[str]) -> None:
    """Install the host guard and the security headers as the application's outermost layers.

    Call it after every other middleware, so nothing ends up outside them.
    """
    app.add_middleware(HostGuard)
    app.add_middleware(SecurityHeaders, is_documentation=documentation_pages.__contains__)
