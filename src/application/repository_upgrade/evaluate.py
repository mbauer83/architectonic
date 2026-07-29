"""EvaluateRepositoryUpgrade: the dry-run/report use case.

Runs every registered step's `detect()` against one repo root and produces the stable report
shape. Never mutates — this is the "always allowed, backend running or not" path.
"""

from __future__ import annotations

from src.application.repository_upgrade.ports import RepoUpgradeView
from src.application.repository_upgrade.registry import FORMAT_CONTRACT_VERSION, StepRegistry
from src.domain.repository.repository_upgrade import AppliedFinding, RepoUpgradeReport


def evaluate_repository(
    view: RepoUpgradeView,
    *,
    registry: StepRegistry,
    software_version: str,
) -> RepoUpgradeReport:
    applied_before = view.applied_step_ids
    results: list[AppliedFinding] = []
    unapplied: list[str] = []
    for step in registry.steps():
        findings = step.detect(view)
        if not findings:
            continue
        unapplied.append(step.id)
        results.extend(AppliedFinding(finding=f, outcome="skipped") for f in findings)
    return RepoUpgradeReport(
        repo_root=str(view.root),
        software_version=software_version,
        format_contract_version=FORMAT_CONTRACT_VERSION,
        available_steps=registry.step_identities(),
        applied_steps_before=tuple(sorted(applied_before)),
        applied_steps_after=tuple(sorted(applied_before)),
        results=tuple(results),
        unapplied_required_steps=tuple(unapplied),
    )
