"""Mutation-authorization contract: intents, targets, health, snapshots, ports.

Every architecture-repository mutation carries a closed intent and a typed target.
A pure policy (``mutation_policy``) decides each request against an immutable
per-operation snapshot of workspace authority state, composed fresh by a provider —
authority is never cached. Infrastructure adapters implement the provider and
executor ports; they are wired only at composition roots.

The sync-health reason vocabulary is owned here, inward: the persisted sync-state
aggregate only serializes it.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypeVar

_T = TypeVar("_T")

MutationIntent = Literal[
    "engagement_authoring",
    "enterprise_admin_authoring",
    "promotion",
    "enterprise_save",
    "enterprise_submit",
    "enterprise_discard",
    "maintenance",
]

SyncHealthReason = Literal[
    "fetch_failed",
    "upstream_missing",
    "diverged",
    "sync_state_unknown",
    "state_file_corrupt",
    "repository_uninitialized",
]

GateBlock = Literal["read_only", "sync_in_progress"]

DenialCode = Literal[
    "read_only",
    "sync_in_progress",
    "sync_health",
    "target_not_engagement_root",
    "target_not_enterprise_root",
    "enterprise_target_forbidden",
    "admin_mode_required",
    "target_shape_mismatch",
]


@dataclass(frozen=True)
class SyncHealth:
    """Enterprise sync health overlay: healthy unless a closed reason is set.

    A dirty working tree is lifecycle state, never a health reason — resolving it
    (``enterprise_save``) must stay authorized.
    """

    reason: SyncHealthReason | None = None
    message: str = ""

    @property
    def blocked(self) -> bool:
        return self.reason is not None


@dataclass(frozen=True)
class RepositoryWrite:
    """Single-root mutation target: authoring, admin authoring, save, submit,
    maintenance. Bulk operations authorize the LIVE destination root here, never
    a staging directory."""

    root: Path


@dataclass(frozen=True)
class PromotionWrite:
    """Promotion writes into the live enterprise destination from an engagement source."""

    source_root: Path
    destination_root: Path


@dataclass(frozen=True)
class DiscardWrite:
    """Enterprise branch discard: ``pending_remote`` marks the remote-touching
    variant (deleting a pushed review branch), distinguishable from local-only
    branch discard for health-fault authorization."""

    root: Path
    pending_remote: bool


MutationTarget = RepositoryWrite | PromotionWrite | DiscardWrite


@dataclass(frozen=True)
class MutationRequest:
    """One mutation to authorize: a closed intent plus its typed target."""

    intent: MutationIntent
    target: MutationTarget


@dataclass(frozen=True)
class MutationAllowed:
    pass


@dataclass(frozen=True)
class MutationDenied:
    code: DenialCode
    message: str
    health_reason: SyncHealthReason | None = None


MutationDecision = MutationAllowed | MutationDenied


class MutationRejected(Exception):
    """Raised by the executor when the policy denies a mutation request."""

    def __init__(self, denial: MutationDenied) -> None:
        self.denial = denial
        super().__init__(denial.message)


@dataclass(frozen=True)
class AuthorizationSnapshot:
    """Immutable per-operation authority state.

    Roots are canonically resolved by the provider; ``gate_block`` is the live
    workspace-gate state at snapshot time; ``sync_health`` is the persisted
    enterprise health overlay.
    """

    engagement_root: Path | None
    enterprise_root: Path | None
    admin_mode: bool
    read_only: bool
    gate_block: GateBlock | None
    sync_health: SyncHealth


class AuthorizationSnapshotProvider(Protocol):
    """Composes a fresh immutable snapshot for every authorization check."""

    def snapshot(self) -> AuthorizationSnapshot: ...


class MutationExecutor(Protocol):
    """The only way any interface executes an architecture-repository mutation.

    Implementations authorize against a fresh snapshot, submit ONCE to the shared
    single-worker queue, re-check a fresh snapshot inside the worker, acquire the
    workspace write gate exactly once around the operation, and surface denials
    as ``MutationRejected``.
    """

    def submit(
        self, request: MutationRequest, operation: Callable[[], _T], *, operation_name: str
    ) -> Future[_T]: ...

    def run(self, request: MutationRequest, operation: Callable[[], _T], *, operation_name: str) -> _T: ...
