"""Ordered, per-target-atomic orchestration over operational upgrade targets.

Phases (the CLI drives them in this order): all-target discovery + physical
dedup, read-only readiness, repository recovery plan, classified pre-existing
consistency repair, re-scan + all-target semantic preflight, then ordered
per-target apply. No cross-target atomicity is claimed: a failure after an
earlier target committed stops the run and yields an accurate partial report;
a rerun resumes safely (detection always re-derives from actual content).
"""

from __future__ import annotations

from src.application.deployment_upgrade.ports import (
    OperationalStepRegistry,
    OperationalTargetHandle,
    OperationalUpgradeStep,
)
from src.domain.repository.operational_upgrade import (
    APPLY_ORDER,
    OperationalTargetReport,
    TargetState,
)
from src.domain.repository.repository_upgrade import AppliedFinding, UpgradeFinding


def dedupe_handles(
    handles: tuple[OperationalTargetHandle, ...],
) -> tuple[OperationalTargetHandle, ...]:
    """Physical dedup: one handle per (kind, canonical location) = stable_id."""
    seen: set[str] = set()
    unique: list[OperationalTargetHandle] = []
    for handle in handles:
        if handle.target.stable_id in seen:
            continue
        seen.add(handle.target.stable_id)
        unique.append(handle)
    return tuple(unique)


def order_handles(
    handles: tuple[OperationalTargetHandle, ...],
) -> tuple[OperationalTargetHandle, ...]:
    """Deterministic apply order: kind order, then declared dependencies, then id."""
    by_kind = sorted(
        handles, key=lambda h: (APPLY_ORDER.index(h.target.kind), h.target.stable_id)
    )
    ordered: list[OperationalTargetHandle] = []
    placed: set[str] = set()
    remaining = list(by_kind)
    while remaining:
        progressed = False
        for handle in list(remaining):
            deps = set(handle.target.dependencies)
            known = {h.target.stable_id for h in by_kind}
            if deps & known <= placed:
                ordered.append(handle)
                placed.add(handle.target.stable_id)
                remaining.remove(handle)
                progressed = True
        if not progressed:  # dependency cycle — deterministic fallback, never a hang
            ordered.extend(remaining)
            break
    return tuple(ordered)


def _uninspectable_finding(handle: OperationalTargetHandle) -> UpgradeFinding:
    return UpgradeFinding(
        step_id="deployment",
        finding_id="target-uninspectable",
        location=handle.target.display_location,
        description=(
            f"{handle.target.kind} target cannot be inspected (credentials unavailable "
            "or unreadable) — its version is unknown, never assumed current"
        ),
        severity="error",
        auto_migratable=False,
        manual_instructions=(
            "Provide the target's credential through the non-interactive secret path "
            "(e.g. the OS keychain / ARCH_ASSURANCE_MASTER_PASSWORD vault) and re-run."
        ),
        blocks_commit=True,
    )


def _detect(
    handle: OperationalTargetHandle, steps: tuple[OperationalUpgradeStep, ...]
) -> list[tuple[OperationalUpgradeStep, list[UpgradeFinding]]]:
    view = handle.view()
    detections = [(step, step.detect(view)) for step in steps]
    return [(step, findings) for step, findings in detections if findings]


def _state_for(results: tuple[AppliedFinding, ...]) -> TargetState:
    if not results:
        return "current"
    if any(r.finding.blocks_commit for r in results):
        return "blocked"
    return "pending"


def evaluate_targets(
    handles: tuple[OperationalTargetHandle, ...],
    registry: OperationalStepRegistry,
) -> tuple[OperationalTargetReport, ...]:
    """Read-only pass over every discovered target (dry-run and commit preflight)."""
    reports: list[OperationalTargetReport] = []
    for handle in order_handles(dedupe_handles(handles)):
        if not handle.inspectable:
            finding = _uninspectable_finding(handle)
            reports.append(
                OperationalTargetReport(
                    target=handle.target,
                    state="uninspectable",
                    results=(AppliedFinding(finding=finding, outcome="skipped"),),
                    detail="deployment readiness NOT certified",
                )
            )
            continue
        detected = _detect(handle, registry.steps_for(handle.target.kind))
        results = tuple(
            AppliedFinding(finding=f, outcome="skipped")
            for _, findings in detected
            for f in findings
        )
        reports.append(
            OperationalTargetReport(target=handle.target, state=_state_for(results), results=results)
        )
    return tuple(reports)


def apply_targets(
    handles: tuple[OperationalTargetHandle, ...],
    registry: OperationalStepRegistry,
) -> tuple[tuple[OperationalTargetReport, ...], str | None]:
    """Ordered apply; one atomic unit of work per target.

    Returns the per-target reports and the stable_id of the first failed target
    (None when everything succeeded). Later targets are not attempted after a
    failure — the rerun resumes from actual content.
    """
    reports: list[OperationalTargetReport] = []
    failed: str | None = None
    for handle in order_handles(dedupe_handles(handles)):
        if failed is not None:
            reports.append(
                OperationalTargetReport(
                    target=handle.target,
                    state="pending",
                    detail="not attempted — an earlier target failed; re-run to resume",
                )
            )
            continue
        report = _apply_one(handle, registry)
        reports.append(report)
        if report.has_errors:
            failed = handle.target.stable_id
    return tuple(reports), failed


def _apply_one(
    handle: OperationalTargetHandle, registry: OperationalStepRegistry
) -> OperationalTargetReport:
    detected = _detect(handle, registry.steps_for(handle.target.kind))
    if not detected:
        return OperationalTargetReport(target=handle.target, state="current")
    results: list[AppliedFinding] = []
    uow = handle.begin()
    try:
        for step, findings in detected:
            manual = [f for f in findings if not f.auto_migratable]
            results.extend(
                AppliedFinding(finding=f, outcome="skipped", detail="manual action required")
                for f in manual
            )
            auto = [f for f in findings if f.auto_migratable]
            if auto:
                results.extend(step.apply(handle.view(), uow, auto))
        if any(r.outcome == "error" for r in results):
            # Per-target atomicity: a reported step error voids the whole unit.
            uow.rollback()
            return OperationalTargetReport(
                target=handle.target, state="pending", results=tuple(results)
            )
        uow.commit()
    except Exception as exc:  # noqa: BLE001 — per-target isolation; unit rolls back whole
        uow.rollback()
        error = UpgradeFinding(
            step_id="deployment",
            finding_id="target-apply-failed",
            location=handle.target.display_location,
            description=f"{handle.target.kind} target migration failed; unit rolled back",
            severity="error",
            auto_migratable=False,
            manual_instructions=f"Investigate and re-run to resume: {exc}",
        )
        return OperationalTargetReport(
            target=handle.target,
            state="pending",
            results=(*results, AppliedFinding(finding=error, outcome="error", detail=str(exc))),
        )
    applied = any(r.outcome == "applied" for r in results)
    return OperationalTargetReport(
        target=handle.target,
        state="current" if applied or not results else _state_for(tuple(results)),
        results=tuple(results),
        committed=applied,
    )
