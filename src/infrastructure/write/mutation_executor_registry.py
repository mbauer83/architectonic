"""Process-wide holder for the installed AuthorizedMutationExecutor.

Both mutation surfaces (MCP tool registration and REST routes) execute through
the one executor installed here by the composition root (backend startup, test
harnesses). A standalone server process whose entrypoint installed none gets a
lazily composed workspace-default executor.
"""

from __future__ import annotations

import threading
from pathlib import Path

from src.infrastructure.write.authorized_mutation_executor import AuthorizedMutationExecutor

_executor_lock = threading.Lock()
_installed_executor: AuthorizedMutationExecutor | None = None


def install_mutation_executor(executor: AuthorizedMutationExecutor) -> None:
    """Install the executor. Called only from composition roots."""
    global _installed_executor
    with _executor_lock:
        _installed_executor = executor


def _reset_executor_for_test() -> None:
    global _installed_executor
    with _executor_lock:
        _installed_executor = None


def authorization_snapshot():
    """A fresh authority snapshot from the installed executor's provider — never
    cached; every status request composes its projection from this."""
    return mutation_executor().snapshot_provider.snapshot()


def mutation_executor() -> AuthorizedMutationExecutor:
    """Return the installed executor, composing a workspace-default one lazily for
    processes whose entrypoint installed none."""
    global _installed_executor
    with _executor_lock:
        if _installed_executor is None:
            _installed_executor = _default_executor()
        return _installed_executor


class _DynamicWorkspaceSnapshots:
    """Fallback provider for processes whose entrypoint installed no executor.

    Unlike the composition-root provider (frozen roots — changing the served
    engagement requires a restart), this one re-reads the live GUI state (or the
    workspace defaults) on every snapshot, so late initialisation and test-harness
    re-initialisation are honoured. Still O(1) per snapshot.
    """

    def snapshot(self):  # -> AuthorizationSnapshot
        from src.application.mutation_authorization import AuthorizationSnapshot, SyncHealth  # noqa: PLC0415
        from src.infrastructure.gui.routers import state as gui_state  # noqa: PLC0415
        from src.infrastructure.mcp.artifact_mcp.context import (  # noqa: PLC0415
            resolve_enterprise_repo_root,
            resolve_repo_root,
        )
        from src.infrastructure.workspace.mutation_gate import get_workspace_gate  # noqa: PLC0415

        engagement = gui_state.maybe_engagement_root() or resolve_repo_root(repo_root=None, repo_preset=None)
        try:
            enterprise: Path | None = gui_state.maybe_enterprise_root() or resolve_enterprise_repo_root(
                enterprise_root=None
            )
        except RuntimeError:
            enterprise = None
        if enterprise is not None:
            from src.infrastructure.write.workspace_authorization import persisted_sync_health  # noqa: PLC0415

            sync_health = persisted_sync_health(enterprise)()
        else:
            sync_health = SyncHealth()
        return AuthorizationSnapshot(
            engagement_root=engagement.resolve(),
            enterprise_root=enterprise.resolve() if enterprise is not None else None,
            admin_mode=gui_state.is_admin_mode(),
            read_only=gui_state.is_read_only(),
            gate_block=get_workspace_gate().block_reason,
            sync_health=sync_health,
        )


def _default_executor() -> AuthorizedMutationExecutor:
    from src.infrastructure.write.authorized_mutation_executor import (  # noqa: PLC0415
        build_workspace_mutation_executor,
    )

    return build_workspace_mutation_executor(_DynamicWorkspaceSnapshots())
