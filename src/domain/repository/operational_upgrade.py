"""Pure value objects for deployment-scoped (multi-target) upgrade orchestration.

Extends the repository upgrade report with operational targets (guidance cache,
signal stores, the deployment settings document). No cross-target atomicity is
claimed anywhere: application is ordered, per-target atomic, idempotent, and
resumable — a failure after an earlier target committed yields an accurate
partial report and a safe rerun.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from src.domain.repository.repository_upgrade import AppliedFinding, WorkspaceUpgradeReport

TargetKind = Literal[
    "repository", "deployment_settings", "guidance_cache", "signals_sqlite", "assurance_sqlcipher"
]
CredentialRequirement = Literal["none", "sqlcipher_key"]
TargetState = Literal["current", "pending", "blocked", "uninspectable", "absent"]
DeploymentApplyOutcome = Literal[
    "success",
    "repository_step_errors",
    "unresolved_migration",
    "partial_apply",
    "infrastructure_failure",
]

REPORT_SCHEMA_VERSION = "2"
"""Moved from "1" when `checkpoint_set` joined the report."""

APPLY_ORDER: tuple[TargetKind, ...] = (
    "repository",
    "guidance_cache",
    "signals_sqlite",
    "assurance_sqlcipher",
    "deployment_settings",
)
"""Deterministic per-kind application order. The settings document commits last so
an operator-visible configuration rewrite always reflects completed store work."""


@dataclass(frozen=True)
class UpgradeTarget:
    """One discovered persisted surface outside repository content."""

    kind: TargetKind
    stable_id: str
    display_location: str
    current_version: int | None
    credential_requirement: CredentialRequirement = "none"
    dependencies: tuple[str, ...] = ()
    configured: bool = True
    """False when the surface exists physically but the active configuration no
    longer selects it (e.g. a legacy public signals file under a co-located
    deployment) — still discovered, reported, and migratable."""


@dataclass(frozen=True)
class OperationalTargetReport:
    target: UpgradeTarget
    state: TargetState
    results: tuple[AppliedFinding, ...] = ()
    committed: bool = False
    detail: str | None = None

    @property
    def has_errors(self) -> bool:
        return any(r.outcome == "error" for r in self.results)

    @property
    def blocking(self) -> bool:
        return any(r.finding.blocks_commit for r in self.results)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.target.kind,
            "stable_id": self.target.stable_id,
            "display_location": self.target.display_location,
            "current_version": self.target.current_version,
            "credential_requirement": self.target.credential_requirement,
            "configured": self.target.configured,
            "state": self.state,
            "committed": self.committed,
            "detail": self.detail,
            "findings": [
                {
                    "step_id": r.finding.step_id,
                    "finding_id": r.finding.finding_id,
                    "location": r.finding.location,
                    "description": r.finding.description,
                    "severity": r.finding.severity,
                    "auto_migratable": r.finding.auto_migratable,
                    "blocks_commit": r.finding.blocks_commit,
                    "rewrite_summary": r.finding.rewrite_summary,
                    "manual_instructions": r.finding.manual_instructions,
                    "outcome": r.outcome,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }


@dataclass(frozen=True)
class DeploymentPreflight:
    """Read-only readiness facts reported before any write."""

    settings_document: str
    settings_source: str
    operator_owned: bool
    notes: tuple[str, ...] = ()
    pre_existing_repairs: tuple[str, ...] = ()
    """Classified pre-existing consistency repair (repository transaction recovery /
    stale-temp sweep) — an existing behavior, reported as such; the no-writes-before-
    preflight guarantee applies to *migration* writes."""

    def to_dict(self) -> dict[str, object]:
        return {
            "settings_document": self.settings_document,
            "settings_source": self.settings_source,
            "operator_owned": self.operator_owned,
            "notes": list(self.notes),
            "pre_existing_repairs": list(self.pre_existing_repairs),
        }


@dataclass(frozen=True)
class RepositoryCheckpoint:
    """One repository's working tree as it was before a commit wrote it, pinned under a git ref."""

    root: str
    ref: str


@dataclass(frozen=True)
class OperationalBackup:
    """One operational target's file copy, taken before a commit wrote it."""

    kind: TargetKind
    location: str
    backup_path: str


@dataclass(frozen=True)
class CheckpointSet:
    """The safety point one `--commit` leaves behind: every target it was about to write, as it was.

    Taken after the backend-not-serving gate and before the first write, so it records the exact
    pre-upgrade state; named by a compact UTC timestamp so `--restore` can address it. Repositories
    are git refs, not copies — a six-figure file count is why — and operational targets are copies,
    because a database has no ref to pin.
    """

    id: str
    repositories: tuple[RepositoryCheckpoint, ...] = ()
    operational: tuple[OperationalBackup, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "repositories": [{"root": r.root, "ref": r.ref} for r in self.repositories],
            "operational": [
                {"kind": o.kind, "location": o.location, "backup_path": o.backup_path} for o in self.operational
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CheckpointSet:
        repositories = data.get("repositories")
        operational = data.get("operational")
        return cls(
            id=str(data["id"]),
            repositories=tuple(
                RepositoryCheckpoint(root=str(r["root"]), ref=str(r["ref"]))
                for r in (repositories if isinstance(repositories, list) else [])
                if isinstance(r, Mapping)
            ),
            operational=tuple(
                OperationalBackup(kind=o["kind"], location=str(o["location"]), backup_path=str(o["backup_path"]))
                for o in (operational if isinstance(operational, list) else [])
                if isinstance(o, Mapping)
            ),
        )


@dataclass(frozen=True)
class DeploymentUpgradeReport:
    """The full additive report: existing `repos` retained, operational sections new."""

    repos: WorkspaceUpgradeReport
    operational_targets: tuple[OperationalTargetReport, ...] = ()
    preflight: DeploymentPreflight | None = None
    outcome: DeploymentApplyOutcome = "success"
    checkpoint_set: CheckpointSet | None = None
    """What a commit recorded before its first write; None for a dry run or a no-op commit."""

    def to_dict(self) -> Mapping[str, object]:
        base: dict[str, object] = dict(self.repos.to_dict())
        base["report_schema_version"] = REPORT_SCHEMA_VERSION
        base["operational_targets"] = [t.to_dict() for t in self.operational_targets]
        base["deployment_preflight"] = self.preflight.to_dict() if self.preflight else None
        base["outcome"] = self.outcome
        base["checkpoint_set"] = self.checkpoint_set.to_dict() if self.checkpoint_set else None
        return base


@dataclass(frozen=True)
class ApplyProgress:
    """What actually happened during an ordered apply, for outcome classification."""

    committed_target_ids: tuple[str, ...] = ()
    failed_target_id: str | None = None
    repository_step_errors: bool = False
    infrastructure_failure: bool = False
    blocking_findings: tuple[str, ...] = field(default_factory=tuple)


def classify_apply_outcome(progress: ApplyProgress) -> DeploymentApplyOutcome:
    """The normative state table (exact precedence).

    - blocking findings anywhere → unresolved_migration (nothing was written);
    - a failure after ≥1 committed target → partial_apply (20 wins over 1: a
      cross-target failure dominates within-repository step errors);
    - a failure before any target commit → infrastructure_failure;
    - repository-internal step errors alone keep the grandfathered code-1 shape;
    - otherwise success.
    """
    if progress.blocking_findings:
        return "unresolved_migration"
    if progress.failed_target_id is not None or progress.infrastructure_failure:
        if progress.committed_target_ids:
            return "partial_apply"
        return "infrastructure_failure"
    if progress.repository_step_errors:
        return "repository_step_errors"
    return "success"
