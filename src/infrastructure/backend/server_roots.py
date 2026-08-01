"""Utility helpers for the GUI / backend server CLI.

The FastAPI application itself is built in ``arch_backend_app._build_app`` — this
module only provides ``resolve_server_roots`` (used by the backend CLI) and a thin
``main()`` shim that delegates to the real entry-point.
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


def main(argv: list[str] | None = None) -> None:
    from src.infrastructure.backend.arch_backend import main as backend_main

    backend_main(argv)


if __name__ == "__main__":
    main()
