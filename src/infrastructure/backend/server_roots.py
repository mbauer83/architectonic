"""Root resolution for the backend server CLI.

The FastAPI application itself is built in ``arch_backend_app._build_app`` and the
entry point is ``arch_backend.main`` — this module only answers where the engagement
and enterprise repositories live.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_server_roots(
    arg_repo_root: str | None,
    arg_enterprise_root: str | None,
) -> tuple[Path | None, Path | None]:
    """Resolve engagement and enterprise roots.

    Priority: explicit CLI arg > environment variable > arch-init state file.
    Environment variables: ARCH_REPO_ROOT, ARCH_ENTERPRISE_ROOT.
    Returns (engagement_root, enterprise_root); either may be None.
    """
    from src.infrastructure.workspace.workspace_init import load_init_state

    ws = load_init_state()

    eng = (
        Path(arg_repo_root)
        if arg_repo_root
        else Path(os.environ["ARCH_REPO_ROOT"])
        if os.environ.get("ARCH_REPO_ROOT")
        else Path(ws["engagement_root"])
        if ws and "engagement_root" in ws
        else None
    )
    ent = (
        Path(arg_enterprise_root)
        if arg_enterprise_root
        else Path(os.environ["ARCH_ENTERPRISE_ROOT"])
        if os.environ.get("ARCH_ENTERPRISE_ROOT")
        else Path(ws["enterprise_root"])
        if ws and "enterprise_root" in ws
        else None
    )
    return eng, ent
