"""Concrete AuthorizedMutationExecutor.

Composes the shared single-worker write queue with the workspace mutation gate:

    authorize (fresh snapshot) → ONE queue submission → fresh re-check inside the
    worker → gate acquired exactly once → execute the operation.

Handlers migrated onto this executor surrender their own queue/gate wrapping —
the executor owns the single submission; nested submission to the single-worker
queue deadlocks and is therefore forbidden by construction, not convention.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from typing import Protocol, TypeVar

from src.application.mutation_authorization import (
    AuthorizationSnapshotProvider,
    MutationDenied,
    MutationRejected,
    MutationRequest,
)
from src.application.mutation_policy import authorize
from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

_T = TypeVar("_T")


class SerializedSubmitter(Protocol):
    """Submission port of the shared single-worker write queue."""

    def __call__(self, operation_name: str, operation: Callable[[], _T]) -> Future[_T]: ...


class AuthorizedMutationExecutor:
    """The only path by which an interface executes an architecture-repository mutation."""

    def __init__(
        self,
        snapshots: AuthorizationSnapshotProvider,
        *,
        submitter: SerializedSubmitter,
        gate: WorkspaceMutationGate,
    ) -> None:
        self._snapshots = snapshots
        self._submitter = submitter
        self._gate = gate

    @property
    def snapshot_provider(self) -> AuthorizationSnapshotProvider:
        """The provider composing fresh per-operation snapshots — status read models
        consume the SAME source of authority the executor enforces."""
        return self._snapshots

    def _authorize_or_raise(self, request: MutationRequest) -> None:
        decision = authorize(self._snapshots.snapshot(), request)
        if isinstance(decision, MutationDenied):
            raise MutationRejected(decision)

    def submit(
        self, request: MutationRequest, operation: Callable[[], _T], *, operation_name: str
    ) -> Future[_T]:
        """Authorize now, then submit once; the worker re-checks a fresh snapshot
        and holds the write gate for exactly the duration of the operation."""
        self._authorize_or_raise(request)

        def _authorized_and_gated() -> _T:
            self._authorize_or_raise(request)
            with self._gate.writing():
                return operation()

        return self._submitter(operation_name, _authorized_and_gated)

    def run(self, request: MutationRequest, operation: Callable[[], _T], *, operation_name: str) -> _T:
        return self.submit(request, operation, operation_name=operation_name).result()


def build_workspace_mutation_executor(
    snapshots: AuthorizationSnapshotProvider,
) -> AuthorizedMutationExecutor:
    """Compose the executor over the process-wide write queue and workspace gate.

    Call only from composition roots.
    """
    from src.infrastructure.mcp.artifact_mcp.write_queue import submit_serialized  # noqa: PLC0415
    from src.infrastructure.workspace.mutation_gate import get_workspace_gate  # noqa: PLC0415

    def _submitter(operation_name: str, operation: Callable[[], _T]) -> Future[_T]:
        return submit_serialized(operation_name, operation)

    return AuthorizedMutationExecutor(snapshots, submitter=_submitter, gate=get_workspace_gate())
