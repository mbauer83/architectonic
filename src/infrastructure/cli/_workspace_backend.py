"""The base URL of the backend serving *this* workspace, for CLI commands that must talk to it.

A command that composes a URL from the configured port asks whichever process holds that port, and on
a machine running two workspaces that is a coin toss. For the assurance commands it was worse than a
wrong answer: `arch-assurance unlock` posts `authorize: true`, so it authorized a *neighbouring*
workspace's backend to open its own confidential store — one workspace's ceremony granting access in
another.

The endpoint comes from the same plan the bridges and the lifecycle use, so it is the backend that
reports serving this workspace's repositories, wherever it ended up. `ARCH_MCP_BACKEND_URL` still wins:
naming a backend is a decision, and a container's roots never match a host workspace's paths.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.domain.deployment.backend_endpoint import AttachToBackend
from src.infrastructure.backend.backend_endpoint import plan_workspace_endpoint
from src.infrastructure.backend.backend_probe import backend_url, configured_backend_url

logger = logging.getLogger(__name__)


def workspace_backend_url(*, cwd: Path | None = None) -> str | None:
    """This workspace's running backend, or None when none is running for it."""
    external = configured_backend_url()
    if external:
        return external
    plan = plan_workspace_endpoint(cwd=cwd or Path.cwd(), may_start=False)
    if isinstance(plan, AttachToBackend):
        return backend_url(plan.port)
    logger.debug("No backend is serving this workspace: %s", plan)
    return None
