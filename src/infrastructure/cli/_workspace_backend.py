"""The backend serving *this* workspace, for CLI commands that must talk to it.

A command that composes a URL from the configured port asks whichever process holds that port, and on
a machine running two workspaces that is a coin toss. For the assurance commands it was worse than a
wrong answer: `arch-assurance unlock` posts `authorize: true`, so it authorized a *neighbouring*
workspace's backend to open its own confidential store — one workspace's ceremony granting access in
another.

The endpoint comes from the same plan the bridges and the lifecycle use, so it is the backend that
reports serving this workspace's repositories, wherever it ended up. `ARCH_MCP_BACKEND_URL` still wins:
naming a backend is a decision, and a container's roots never match a host workspace's paths.

Every CLI command locates its backend here; `backend_write` is how it then talks to it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.domain.deployment.backend_endpoint import AttachToBackend
from src.domain.deployment.endpoint_vocabulary import BackendIdentity
from src.infrastructure.backend.backend_endpoint import plan_workspace_endpoint
from src.infrastructure.backend.backend_probe import backend_url, configured_backend_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NamedBackend:
    """The backend `ARCH_MCP_BACKEND_URL` names: whatever roots it reports are its own decision."""

    url: str


@dataclass(frozen=True)
class AttachedBackend:
    """The backend the workspace plan attaches to, with what it reported serving where it said."""

    url: str
    identity: BackendIdentity | None


type WorkspaceBackend = NamedBackend | AttachedBackend


def workspace_backend(*, cwd: Path | None = None) -> WorkspaceBackend | None:
    """The backend serving the workspace at *cwd* (default: here), or None when none is running for it."""
    external = configured_backend_url()
    if external:
        return NamedBackend(external)
    plan = plan_workspace_endpoint(cwd=cwd or Path.cwd(), may_start=False)
    if isinstance(plan, AttachToBackend):
        return AttachedBackend(backend_url(plan.port), plan.identity)
    logger.debug("No backend is serving this workspace: %s", plan)
    return None


def workspace_backend_url(*, cwd: Path | None = None) -> str | None:
    """This workspace's running backend's base URL, or None when none is running for it."""
    found = workspace_backend(cwd=cwd)
    return found.url if found is not None else None
