"""Pure value objects for the `arch-repair upgrade` framework.

An `UpgradeStep` (declared in `src.application.repository_upgrade`) scans one persisted-format
surface of a repository and reports `UpgradeFinding`s; applying a step yields `AppliedFinding`s.
`RepoUpgradeReport`/`WorkspaceUpgradeReport` are the stable shapes rendered as human output and
the `--json` contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["error", "warning", "info"]
ScannedSurface = Literal[
    "profiles",
    "customizations",
    "entity_frontmatter",
    "connection_declarations",
    "diagram_frontmatter",
    "group_registry",
    "modification_stamps",
]
FindingOutcome = Literal["applied", "skipped", "error"]

COVERAGE_NOTE = (
    "This report reflects only migrations this software's registered upgrade steps "
    "recognize — it does not certify the repo is fully current. Repos predating the "
    "supported floor (see docs/reference/cli-and-backend.md) are out of scope; a clean "
    "report means \"no known issues\", not \"fully current\"."
)


@dataclass(frozen=True)
class StepIdentity:
    id: str
    version: int


@dataclass(frozen=True)
class UpgradeFinding:
    """One thing a step's `detect()` found that must change."""

    step_id: str
    finding_id: str
    location: str
    description: str
    severity: Severity
    auto_migratable: bool
    rewrite_summary: str | None = None
    manual_instructions: str | None = None
    blocks_commit: bool = False
    """True when this finding makes a COMMIT run unsafe as a whole: the upgrade must
    either complete in full or change nothing, so a commit with any blocking finding
    anywhere in the workspace exits with the distinct unresolved-migration status and
    writes nothing — not even other steps' mechanical rewrites. Ordinary informational
    scan findings never set this."""

    def __post_init__(self) -> None:
        if self.auto_migratable and not self.rewrite_summary:
            raise ValueError(
                f"{self.finding_id}: auto_migratable findings must declare rewrite_summary"
            )
        if not self.auto_migratable and not self.manual_instructions:
            raise ValueError(
                f"{self.finding_id}: non-auto-migratable findings must declare manual_instructions "
                "(findings are never silently skipped)"
            )


@dataclass(frozen=True)
class AppliedFinding:
    finding: UpgradeFinding
    outcome: FindingOutcome
    detail: str | None = None


@dataclass(frozen=True)
class RepoUpgradeReport:
    repo_root: str
    software_version: str
    format_contract_version: str
    available_steps: tuple[StepIdentity, ...]
    applied_steps_before: tuple[str, ...]
    applied_steps_after: tuple[str, ...]
    results: tuple[AppliedFinding, ...] = field(default_factory=tuple)
    unapplied_required_steps: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_errors(self) -> bool:
        return any(r.outcome == "error" for r in self.results)

    @property
    def touched_locations(self) -> frozenset[str]:
        """Repo-relative paths this run would actually rewrite — excludes synthetic
        infrastructure findings (`step_id == "infrastructure"`, which name the repo root,
        not a file) and non-auto-migratable findings (which are never written, only
        reported), so a manual-only finding never falsely shows up as a dirty-file
        collision for a file `--commit` won't touch."""
        return frozenset(
            r.finding.location
            for r in self.results
            if r.finding.step_id != "infrastructure" and r.finding.auto_migratable
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "software_version": self.software_version,
            "format_contract_version": self.format_contract_version,
            "coverage_note": COVERAGE_NOTE,
            "available_steps": [{"id": s.id, "version": s.version} for s in self.available_steps],
            "applied_steps_before": list(self.applied_steps_before),
            "applied_steps_after": list(self.applied_steps_after),
            "unapplied_required_steps": list(self.unapplied_required_steps),
            "findings": [
                {
                    "step_id": r.finding.step_id,
                    "finding_id": r.finding.finding_id,
                    "location": r.finding.location,
                    "description": r.finding.description,
                    "severity": r.finding.severity,
                    "auto_migratable": r.finding.auto_migratable,
                    "rewrite_summary": r.finding.rewrite_summary,
                    "manual_instructions": r.finding.manual_instructions,
                    "outcome": r.outcome,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }


@dataclass(frozen=True)
class WorkspaceUpgradeReport:
    per_repo: tuple[RepoUpgradeReport, ...]

    @property
    def has_errors(self) -> bool:
        return any(r.has_errors for r in self.per_repo)

    def to_dict(self) -> dict[str, object]:
        return {"repos": [r.to_dict() for r in self.per_repo]}
