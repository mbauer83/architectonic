"""ApplyRepositoryUpgrade: the `--commit` use case.

Runs every registered step whose `detect()` reports findings, applies it through the write/
index ports, rebuilds the index once, and stamps the repo's `.arch-repo/config.yaml`. A repo
that is already fully up to date touches nothing at all — no rewrites, no index rebuild, no
config write — so `--commit` is a true no-op and safe to run unconditionally (e.g. as a
pre-start check in a deployment) on a repo nothing needs to change in.
"""

from __future__ import annotations

from src.application.repository_upgrade.ports import RepoUpgradeView, RepoUpgradeWriter
from src.application.repository_upgrade.registry import FORMAT_CONTRACT_VERSION, StepRegistry
from src.domain.repository.repository_upgrade import AppliedFinding, RepoUpgradeReport, UpgradeFinding


def _infra_error(finding_id: str, detail: str) -> AppliedFinding:
    finding = UpgradeFinding(
        step_id="infrastructure",
        finding_id=finding_id,
        location="<repo root>",
        description="Post-apply infrastructure step failed",
        severity="error",
        auto_migratable=False,
        manual_instructions=f"Re-run `arch-repair upgrade --commit`; if it recurs, investigate: {detail}",
    )
    return AppliedFinding(finding=finding, outcome="error", detail=detail)


def apply_repository(
    view: RepoUpgradeView,
    writer: RepoUpgradeWriter,
    *,
    registry: StepRegistry,
    software_version: str,
) -> RepoUpgradeReport:
    applied_before = view.applied_step_ids
    recorded_format_contract_version = view.recorded_format_contract_version
    applied_after = set(applied_before)
    results: list[AppliedFinding] = []
    rewrote_anything = False

    for step in registry.steps():
        findings = step.detect(view)
        if not findings:
            continue

        # Manual-only findings never reach step.apply() — every step can assume it is only
        # ever handed findings it declared auto_migratable itself, so no step has to
        # re-implement this filter.
        manual_findings = [f for f in findings if not f.auto_migratable]
        results.extend(
            AppliedFinding(finding=f, outcome="skipped", detail="not auto-migratable — manual action required")
            for f in manual_findings
        )
        auto_findings = [f for f in findings if f.auto_migratable]
        if not auto_findings:
            continue

        try:
            outcomes = step.apply(view, writer, auto_findings)
        except Exception as exc:  # noqa: BLE001 — isolate one bad step from the rest
            results.extend(
                AppliedFinding(finding=f, outcome="error", detail=str(exc)) for f in auto_findings
            )
            continue
        results.extend(outcomes)
        if any(o.outcome == "applied" for o in outcomes):
            rewrote_anything = True
            applied_after.add(step.id)

    if rewrote_anything:
        try:
            writer.rebuild_index()
        except Exception as exc:  # noqa: BLE001 — surfaced as a report finding, not a crash
            results.append(_infra_error("index-rebuild-failed", str(exc)))

    stamp_needed = (
        applied_after != applied_before
        or recorded_format_contract_version != FORMAT_CONTRACT_VERSION
    )
    if stamp_needed:
        try:
            writer.stamp_applied_steps(
                frozenset(applied_after), format_contract_version=FORMAT_CONTRACT_VERSION
            )
        except Exception as exc:  # noqa: BLE001 — surfaced as a report finding, not a crash
            results.append(_infra_error("config-stamp-failed", str(exc)))

    unapplied = [step.id for step in registry.steps() if step.detect(view) and step.id not in applied_after]
    return RepoUpgradeReport(
        repo_root=str(view.root),
        software_version=software_version,
        format_contract_version=FORMAT_CONTRACT_VERSION,
        available_steps=registry.step_identities(),
        applied_steps_before=tuple(sorted(applied_before)),
        applied_steps_after=tuple(sorted(applied_after)),
        results=tuple(results),
        unapplied_required_steps=tuple(unapplied),
    )
