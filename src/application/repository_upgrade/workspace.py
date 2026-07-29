"""Multi-repo aggregation for `arch-repair upgrade --workspace`.

Each repo root is evaluated/applied independently (one unit = one repo root). A target
raising unexpectedly (foreseeable failure modes already isolated inside `apply_repository`
itself — this is defense-in-depth for anything that still escapes) never discards the
reports already collected for other targets; it is captured as an error entry for that
target's report instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.repository_upgrade.apply import apply_repository
from src.application.repository_upgrade.evaluate import evaluate_repository
from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.registry import FORMAT_CONTRACT_VERSION, StepRegistry
from src.domain.repository.repository_upgrade import (
    AppliedFinding,
    RepoUpgradeReport,
    UpgradeFinding,
    WorkspaceUpgradeReport,
)


@dataclass(frozen=True)
class RepoUpgradeTarget:
    view: RepoUpgradeView
    writer: RepoUpgradeWriter


def _failed_report(view: RepoUpgradeView, software_version: str, exc: Exception) -> RepoUpgradeReport:
    finding = UpgradeFinding(
        step_id="infrastructure",
        finding_id="repo-evaluation-failed",
        location=str(view.root),
        description="This repo root could not be evaluated",
        severity="error",
        auto_migratable=False,
        manual_instructions=f"Investigate and re-run for this repo root: {exc}",
    )
    return RepoUpgradeReport(
        repo_root=str(view.root),
        software_version=software_version,
        format_contract_version=FORMAT_CONTRACT_VERSION,
        available_steps=(),
        applied_steps_before=(),
        applied_steps_after=(),
        results=(AppliedFinding(finding=finding, outcome="error", detail=str(exc)),),
        unapplied_required_steps=(),
    )


def evaluate_workspace(
    targets: list[RepoUpgradeTarget],
    *,
    registry: StepRegistry,
    software_version: str,
) -> WorkspaceUpgradeReport:
    reports: list[RepoUpgradeReport] = []
    for target in targets:
        try:
            reports.append(
                evaluate_repository(target.view, registry=registry, software_version=software_version)
            )
        except Exception as exc:  # noqa: BLE001 — one repo's failure must not lose the rest
            reports.append(_failed_report(target.view, software_version, exc))
    return WorkspaceUpgradeReport(per_repo=tuple(reports))


def apply_workspace(
    targets: list[RepoUpgradeTarget],
    *,
    registry: StepRegistry,
    software_version: str,
) -> WorkspaceUpgradeReport:
    reports: list[RepoUpgradeReport] = []
    for target in targets:
        try:
            reports.append(
                apply_repository(
                    target.view, target.writer, registry=registry, software_version=software_version
                )
            )
        except Exception as exc:  # noqa: BLE001 — one repo's failure must not lose the rest
            reports.append(_failed_report(target.view, software_version, exc))
    return WorkspaceUpgradeReport(per_repo=tuple(reports))
