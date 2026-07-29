"""Deployment upgrade report shape (additive JSON) + the normative outcome table."""

from __future__ import annotations

import pytest

from src.domain.repository.operational_upgrade import (
    ApplyProgress,
    DeploymentUpgradeReport,
    OperationalTargetReport,
    UpgradeTarget,
    classify_apply_outcome,
)
from src.domain.repository.repository_upgrade import (
    AppliedFinding,
    RepoUpgradeReport,
    UpgradeFinding,
    WorkspaceUpgradeReport,
)


def _repo_report() -> RepoUpgradeReport:
    return RepoUpgradeReport(
        repo_root="/repo",
        software_version="x",
        format_contract_version="1",
        available_steps=(),
        applied_steps_before=(),
        applied_steps_after=(),
    )


def _target(kind: str = "guidance_cache") -> UpgradeTarget:
    return UpgradeTarget(
        kind=kind,  # type: ignore[arg-type]
        stable_id=f"{kind}:/x",
        display_location="/x",
        current_version=1,
    )


class TestReportShape:
    def test_repos_key_is_retained_and_new_sections_are_additive(self) -> None:
        report = DeploymentUpgradeReport(repos=WorkspaceUpgradeReport(per_repo=(_repo_report(),)))
        payload = report.to_dict()
        assert isinstance(payload["repos"], list)  # existing consumers keep working
        assert payload["report_schema_version"] == "1"
        assert payload["operational_targets"] == []
        assert payload["deployment_preflight"] is None
        assert payload["outcome"] == "success"

    def test_operational_target_entry_carries_identity_state_and_findings(self) -> None:
        finding = UpgradeFinding(
            step_id="s",
            finding_id="f",
            location="/x",
            description="d",
            severity="warning",
            auto_migratable=False,
            manual_instructions="do it",
        )
        entry = OperationalTargetReport(
            target=_target(),
            state="pending",
            results=(AppliedFinding(finding=finding, outcome="skipped"),),
        ).to_dict()
        assert entry["kind"] == "guidance_cache"
        assert entry["state"] == "pending"
        assert entry["current_version"] == 1
        findings = entry["findings"]
        assert isinstance(findings, list)
        assert findings[0]["finding_id"] == "f"


class TestOutcomeTable:
    @pytest.mark.parametrize(
        ("progress", "expected"),
        [
            (ApplyProgress(), "success"),
            (ApplyProgress(blocking_findings=("b",)), "unresolved_migration"),
            # Repository-internal step errors keep the grandfathered code-1 shape.
            (ApplyProgress(repository_step_errors=True), "repository_step_errors"),
            # A later target failing after ≥1 committed unit dominates everything else.
            (
                ApplyProgress(
                    committed_target_ids=("repository:/r",),
                    failed_target_id="signals_sqlite:/s",
                    repository_step_errors=True,
                ),
                "partial_apply",
            ),
            # A failure before any commit is an infrastructure failure, not partial.
            (ApplyProgress(failed_target_id="guidance_cache:/g"), "infrastructure_failure"),
            (ApplyProgress(infrastructure_failure=True), "infrastructure_failure"),
            (
                ApplyProgress(committed_target_ids=("a",), infrastructure_failure=True),
                "partial_apply",
            ),
        ],
    )
    def test_classification(self, progress: ApplyProgress, expected: str) -> None:
        assert classify_apply_outcome(progress) == expected
