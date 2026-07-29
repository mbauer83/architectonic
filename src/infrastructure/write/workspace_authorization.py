"""Workspace-backed authorization snapshot provider.

Composes a fresh immutable ``AuthorizationSnapshot`` per operation from the
configured repository roots, the backend mode flags, the live workspace mutation
gate, and the persisted enterprise sync health. Constructed only at composition
roots and injected into the ``AuthorizedMutationExecutor``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.mutation_authorization import AuthorizationSnapshot, SyncHealth
from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate


def _healthy() -> SyncHealth:
    return SyncHealth()


def persisted_sync_health(enterprise_root: Path) -> Callable[[], SyncHealth]:
    """Reader over the persisted enterprise sync aggregate's health overlay.

    Uses the aggregate's mtime-validated cache, so each snapshot costs one
    stat() — O(1), model-size independent.
    """

    def read() -> SyncHealth:
        from src.infrastructure.git import enterprise_sync_state  # noqa: PLC0415

        record = enterprise_sync_state.load_cached(enterprise_root).health
        if record is None:
            return SyncHealth()
        return SyncHealth(reason=record.reason, message=record.message)

    return read


class WorkspaceAuthorizationSnapshots:
    """Fresh per-operation snapshots — authority is never cached here.

    ``sync_health`` is a callable so every snapshot re-reads the persisted health
    overlay; it defaults to healthy until a persisted-health reader is wired in.

    Performance contract: snapshots are composed on EVERY mutation (twice — at
    submission and again inside the worker) and on every status request, so every
    input must be O(1) and independent of model size: roots are resolved once at
    construction, the gate read is a single uncontended lock acquisition, and any
    injected ``sync_health`` reader must serve from process memory kept current by
    the persisting aggregate — never a per-call file parse or git invocation.
    Serialized writes are file-I/O-bound (milliseconds); authorization must stay
    microseconds so it never becomes the write queue's bottleneck.
    """

    def __init__(
        self,
        *,
        engagement_root: Path,
        enterprise_root: Path | None,
        admin_mode: bool,
        read_only: bool,
        gate: WorkspaceMutationGate,
        sync_health: Callable[[], SyncHealth] = _healthy,
    ) -> None:
        self._engagement_root = engagement_root.resolve()
        self._enterprise_root = enterprise_root.resolve() if enterprise_root is not None else None
        self._admin_mode = admin_mode
        self._read_only = read_only
        self._gate = gate
        self._sync_health = sync_health

    def snapshot(self) -> AuthorizationSnapshot:
        return AuthorizationSnapshot(
            engagement_root=self._engagement_root,
            enterprise_root=self._enterprise_root,
            admin_mode=self._admin_mode,
            read_only=self._read_only,
            gate_block=self._gate.block_reason,
            sync_health=self._sync_health(),
        )
