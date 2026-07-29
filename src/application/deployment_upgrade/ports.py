"""Ports for deployment-scoped operational upgrade targets.

Operational targets (guidance cache, signal stores, the deployment settings
document) are never forced through `RepoUpgradeWriter` — each kind gets its own
view/unit-of-work pair. Databases migrate through one transactional migration
connection per target; text-file targets write atomically (temp + rename).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.domain.guidance.guidance_hierarchy import GuidanceHierarchy
from src.domain.repository.operational_upgrade import TargetKind, UpgradeTarget
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding


class OperationalTargetView(Protocol):
    """Read-only access to one operational target for a step's `detect()`."""

    @property
    def target(self) -> UpgradeTarget: ...

    def read_text(self, relative_path: str = "") -> str | None:
        """File targets: contents (empty relative path = the target file itself).
        Directory targets: contents of one member file. None when absent."""
        ...

    def list_files(self, relative_glob: str) -> list[str]:
        """Directory targets: member files (sorted, POSIX relative). File targets: []."""
        ...

    def query_scalar(self, sql: str, parameters: tuple[object, ...] = ()) -> object | None:
        """Database targets: one scalar through the read-only inspection connection.
        Text-file targets raise `NotImplementedError`."""
        ...


class OperationalTargetUnitOfWork(Protocol):
    """The only mutation surface for one target — one atomic unit per target."""

    def write_text(self, relative_path: str, content: str) -> None:
        """Stage an atomic text write (temp + rename on commit)."""
        ...

    def execute_sql(self, sql: str, parameters: tuple[object, ...] = ()) -> None:
        """Stage SQL inside the target's single migration transaction."""
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class OperationalUpgradeStep(Protocol):
    """One versioned migration for one target kind (registered per owning WU)."""

    id: str
    version: int
    kind: TargetKind
    description: str

    def detect(self, view: OperationalTargetView) -> list[UpgradeFinding]:
        """Pure: no I/O beyond reading through *view*, no mutation."""
        ...

    def apply(
        self,
        view: OperationalTargetView,
        uow: OperationalTargetUnitOfWork,
        findings: list[UpgradeFinding],
    ) -> list[AppliedFinding]:
        """Rewrite every auto-migratable finding through *uow*; idempotent.
        The framework commits/rolls back the unit of work — steps never do."""
        ...


class OperationalTargetHandle(Protocol):
    """One discovered physical target bound to its per-kind I/O adapters."""

    @property
    def target(self) -> UpgradeTarget: ...

    @property
    def inspectable(self) -> bool:
        """False when the target exists but cannot be read (e.g. locked SQLCipher
        store without a non-interactive credential) — a blocking unresolved
        migration in commit mode, `uninspectable` in dry-run."""
        ...

    def view(self) -> OperationalTargetView: ...

    def begin(self) -> OperationalTargetUnitOfWork: ...


class OperationalStepRegistry:
    """Registered operational migration steps, ordered per kind."""

    def __init__(self) -> None:
        self._steps: dict[str, OperationalUpgradeStep] = {}

    def register(self, step: OperationalUpgradeStep) -> None:
        if step.id in self._steps:
            raise ValueError(f"Operational upgrade step id already registered: {step.id!r}")
        self._steps[step.id] = step

    def steps_for(self, kind: TargetKind) -> tuple[OperationalUpgradeStep, ...]:
        return tuple(sorted((s for s in self._steps.values() if s.kind == kind), key=lambda s: s.version))

    def steps(self) -> tuple[OperationalUpgradeStep, ...]:
        return tuple(self._steps.values())


def build_operational_registry(
    *, guidance_hierarchies: Mapping[str, GuidanceHierarchy] | None = None
) -> OperationalStepRegistry:
    """The full operational step catalog (composition-root style, like
    `build_registry` for repository steps).

    ``guidance_hierarchies`` (alias → declared guidance tree) is what lets the guidance-cache
    migration re-nest each entity type under the domain its module declares. Omitting it leaves
    that step able to detect an outdated cache but not rewrite it, so the caller that can resolve
    the modules — the arch-repair CLI — passes them in."""
    from src.application.deployment_upgrade.steps.assurance_relationship_reconciliation import (  # noqa: PLC0415
        AssuranceRelationshipReconciliationStep,
    )
    from src.application.deployment_upgrade.steps.guidance_cache_format import (  # noqa: PLC0415
        GuidanceCacheFormatStep,
    )
    from src.application.deployment_upgrade.steps.signals_snapshot_schema import (  # noqa: PLC0415
        PublicSqliteSignalsSchemaStep,
        SignalsSnapshotSchemaStep,
    )

    registry = OperationalStepRegistry()
    registry.register(AssuranceRelationshipReconciliationStep())
    registry.register(GuidanceCacheFormatStep(guidance_hierarchies))
    registry.register(SignalsSnapshotSchemaStep())
    registry.register(PublicSqliteSignalsSchemaStep())
    return registry
