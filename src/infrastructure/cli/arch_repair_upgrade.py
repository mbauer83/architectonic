"""`arch-repair upgrade` subcommand: version-aware repo upgrade.

Dry-run/report is always allowed (backend running or not) and never mutates. `--commit`, in
order:
  1. refuses when a backend serves the target repo — the **only** hard, non-overridable
     gate. This is the actual consistency invariant: two writers touching the same files.
     Runs before anything else touches disk.
  2. sweeps orphaned atomic-write temp files a previous, killed run may have left behind;
  3. recovers any transaction left mid-flight by a crashed backend (the same idempotent
     `recover_transactions` the backend itself runs at startup), so upgrade steps always see a
     consistent repo regardless of git-sync/promotion history;
  4. applies. Git status is deliberately **not** a gate. An out-of-date-and-actively-used
     repo — the exact situation this command exists for — routinely has uncommitted edits to
     the very files that need migrating (entity frontmatter, profiles, connection
     declarations); requiring a clean tree first would make `--commit` fail on the common
     case, not the rare one. It's also not a safety property: every step does
     read-current-content → transform → write-back against whatever is on disk *right now*,
     committed or not, so an uncommitted edit is carried forward into the rewrite, never
     clobbered or lost — git cleanliness has no bearing on correctness here, only on how easy
     the resulting diff is to read. So a touched-file/dirty-file overlap is reported as an
     informational note (which files, so the operator knows to review the combined diff
     before committing) and nothing more.

Resumability: every step's `detect()` re-derives its finding from actual repo content, never
from the `.arch-repo/config.yaml` applied-steps stamp — the stamp is metadata for reporting
only. Combined with atomic (temp+rename) writes and per-step/per-repo failure isolation (see
`apply.py`/`workspace.py`), this means `--commit` may be interrupted at any point (killed
process, crash, power loss) and safely re-run from scratch: partially-applied repos, stale
stamps, and stray temp files are all self-healing on the next invocation.
See `src.infrastructure.repository_upgrade.guard`.
"""

from __future__ import annotations

import argparse
import os
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Literal, cast

from src.application.deployment_upgrade.orchestrate import apply_targets, evaluate_targets
from src.application.deployment_upgrade.ports import (
    OperationalStepRegistry,
    build_operational_registry,
)
from src.application.repository_upgrade.canonical_ids import canonical_index
from src.application.repository_upgrade.registry import StepRegistry, build_registry
from src.application.repository_upgrade.workspace import (
    RepoUpgradeTarget,
    apply_workspace,
    evaluate_workspace,
)
from src.domain.deployment.layout import DeploymentLayoutConflict
from src.domain.repository.operational_upgrade import (
    ApplyProgress,
    DeploymentApplyOutcome,
    DeploymentPreflight,
    DeploymentUpgradeReport,
    classify_apply_outcome,
)
from src.infrastructure.app_bootstrap import build_module_registry, guidance_hierarchies
from src.infrastructure.backend.backend_probe import (
    backend_url,
    configured_backend_url,
    probe_backend_url,
    resolve_backend_port,
)
from src.infrastructure.cli._upgrade_deployment import (
    DeploymentSide,
    add_deployment_arguments,
    build_deployment_side,
    operational_blocking_findings,
)
from src.infrastructure.cli._upgrade_repo_phases import (
    emit_deployment,
    note_dirty_overlap,
    sweep_and_recover,
)
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)
from src.infrastructure.repository_upgrade.guard import (
    check_backend_not_serving,
    probe_backend_identity,
)
from src.infrastructure.workspace.workspace_init import load_init_state


def software_version() -> str:
    try:
        return _pkg_version("architectonic")
    except PackageNotFoundError:
        return "unknown"


EXIT_UNRESOLVED_MIGRATION = 3
"""Distinct commit-mode exit status: a finding that blocks the whole commit (e.g. a
divergent viewpoint selection with no --resolve-selection choice) was present — nothing
was written anywhere; the report lists the required choices."""

EXIT_PARTIAL_APPLY = 20
"""Commit mode: at least one complete target unit committed, then a LATER target
failed. Wins over the repository code-1 semantics (a cross-target failure dominates
within-repository step errors). The report is an exact partial record with resume
instructions — re-running resumes safely."""

EXIT_INFRASTRUCTURE_FAILURE = 21
"""Commit mode: infrastructure/credential failure before any target commit — no
migration writes happened (separately reported pre-existing consistency repair may
have written)."""

_EXIT_BY_OUTCOME: dict[DeploymentApplyOutcome, int] = {
    "success": 0,
    "repository_step_errors": 1,
    "unresolved_migration": EXIT_UNRESOLVED_MIGRATION,
    "partial_apply": EXIT_PARTIAL_APPLY,
    "infrastructure_failure": EXIT_INFRASTRUCTURE_FAILURE,
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="arch-repair upgrade",
        description="Detect and (with --commit) apply persisted-format upgrades for one or more repo roots.",
    )
    p.add_argument("--repo-root", action="append", default=[], metavar="PATH")
    p.add_argument("--workspace", metavar="PATH", help="Resolve engagement + enterprise roots from arch-init state")
    p.add_argument("--commit", action="store_true", default=False)
    p.add_argument("--json", action="store_true", default=False, dest="json_output")
    p.add_argument(
        "--resolve-selection",
        action="append",
        default=[],
        metavar="SLUG=scope|query",
        help=(
            "Resolve one divergent viewpoint's active selection layer (repeatable). "
            "Writes ONLY that definition's selection_mode — never a semantic conversion."
        ),
    )
    add_deployment_arguments(p)
    return p


def parse_selection_resolutions(raw: list[str]) -> dict[str, Literal["scope", "query"]]:
    resolutions: dict[str, Literal["scope", "query"]] = {}
    for item in raw:
        slug, separator, mode = item.partition("=")
        if not separator or mode not in ("scope", "query") or not slug:
            raise SystemExit(f"ERROR: --resolve-selection expects SLUG=scope|query, got {item!r}")
        resolutions[slug] = cast(Literal["scope", "query"], mode)
    return resolutions


def resolve_repo_roots(
    *, repo_root: list[str], workspace: str | None, allow_empty: bool = False
) -> list[Path]:
    roots = [Path(p).resolve() for p in repo_root]
    if workspace is not None:
        state = load_init_state(Path(workspace).resolve())
        if state is None:
            raise SystemExit(f"ERROR: no arch-init state found under {workspace}")
        roots.append(Path(state["engagement_root"]).resolve())
        roots.append(Path(state["enterprise_root"]).resolve())
    if not roots and not allow_empty:
        raise SystemExit("ERROR: specify --repo-root (repeatable) and/or --workspace")
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def main_upgrade(
    argv: list[str],
    *,
    registry: StepRegistry | None = None,
    operational_registry: OperationalStepRegistry | None = None,
) -> int:
    args = parser().parse_args(argv)
    if registry is None:
        registry = build_registry(parse_selection_resolutions(args.resolve_selection))

    # Phase 1 — deployment identity + operational target discovery (with physical
    # dedup). A layout conflict is a hard error before any target is opened.
    try:
        side = build_deployment_side(args, os.environ)
    except DeploymentLayoutConflict as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    roots = resolve_repo_roots(
        repo_root=args.repo_root, workspace=args.workspace, allow_empty=side.active
    )
    version = software_version()
    targets = [RepoUpgradeTarget(FilesystemRepoUpgradeView(r), FilesystemRepoUpgradeWriter(r)) for r in roots]

    if operational_registry is None:
        # Built after the roots are known: the confidential store cannot look up how an
        # architecture artifact is spelled now — it never reads the repository — so the join
        # is made here, where both sides are already open, and handed to the step.
        operational_registry = build_operational_registry(
            guidance_hierarchies=guidance_hierarchies(build_module_registry()),
            canonical_entity_ids=canonical_index([target.view for target in targets]),
        )

    if not args.commit:
        # Dry-run is always exit 0 — findings, blockers, and uninspectable targets are
        # report states, never exit codes (existing automation reads 0 as "evaluated").
        repo_report = evaluate_workspace(targets, registry=registry, software_version=version)
        operational = evaluate_targets(side.handles, operational_registry)
        emit_deployment(
            DeploymentUpgradeReport(
                repos=repo_report, operational_targets=operational, preflight=side.preflight
            ),
            args.json_output,
        )
        return 0

    # Phase 2 — read-only readiness: the hard backend-serving guard (repositories).
    for root in roots:
        _guard_backend_not_serving(root)

    # Phases 3–4 — repository recovery plan + classified pre-existing consistency
    # repair (stale-temp sweep, transaction recovery). These are existing repair
    # behaviors reported as such; the no-writes-before-preflight guarantee applies
    # to *migration* writes.
    repairs: list[str] = []
    for root in roots:
        repairs.extend(sweep_and_recover(root))

    # Phase 5 — re-scan + all-target semantic preflight: a commit-blocking finding
    # ANYWHERE (repository or operational) means the upgrade must not write anything;
    # the run either completes in full or changes nothing and fails loudly.
    gate_report = evaluate_workspace(targets, registry=registry, software_version=version)
    gate_operational = evaluate_targets(side.handles, operational_registry)
    blocking = [
        result.finding
        for repo_report in gate_report.per_repo
        for result in repo_report.results
        if result.finding.blocks_commit
    ] + operational_blocking_findings(gate_operational)
    preflight = _preflight_with_repairs(side, repairs)
    if blocking:
        print("UNRESOLVED MIGRATION — nothing was written. Required choices:", file=sys.stderr)
        for finding in blocking:
            print(f"  {finding.finding_id}: {finding.description}", file=sys.stderr)
            if finding.manual_instructions:
                print(f"    → {finding.manual_instructions}", file=sys.stderr)
        return EXIT_UNRESOLVED_MIGRATION

    # Informational dirty-overlap notes — see the module docstring for why git
    # status is not a safety gate here.
    for root, repo_report in zip(roots, gate_report.per_repo, strict=True):
        note_dirty_overlap(root, repo_report.touched_locations)
        print(f"Backup/branch recommendation: commit or branch {root} before proceeding.", file=sys.stderr)

    # Phase 6 — ordered per-target apply: repositories first (existing semantics,
    # grandfathered per-repo isolation), then operational targets in kind order.
    repo_report_applied = apply_workspace(targets, registry=registry, software_version=version)
    committed = [
        f"repository:{r.repo_root}"
        for r in repo_report_applied.per_repo
        if not r.has_errors and any(result.outcome == "applied" for result in r.results)
    ]
    operational_applied, failed_target = apply_targets(side.handles, operational_registry)
    committed.extend(r.target.stable_id for r in operational_applied if r.committed)
    outcome = classify_apply_outcome(
        ApplyProgress(
            committed_target_ids=tuple(committed),
            failed_target_id=failed_target,
            repository_step_errors=repo_report_applied.has_errors,
        )
    )
    emit_deployment(
        DeploymentUpgradeReport(
            repos=repo_report_applied,
            operational_targets=operational_applied,
            preflight=preflight,
            outcome=outcome,
        ),
        args.json_output,
    )
    return _EXIT_BY_OUTCOME[outcome]


def _preflight_with_repairs(side: DeploymentSide, repairs: list[str]) -> DeploymentPreflight:
    base = side.preflight or DeploymentPreflight(
        settings_document="", settings_source="", operator_owned=False
    )
    return DeploymentPreflight(
        settings_document=base.settings_document,
        settings_source=base.settings_source,
        operator_owned=base.operator_owned,
        notes=base.notes,
        pre_existing_repairs=tuple(repairs),
    )


def _guard_backend_not_serving(repo_root: Path) -> None:
    base_url = configured_backend_url() or backend_url(resolve_backend_port())
    responding = probe_backend_url(base_url)
    identity = probe_backend_identity(base_url) if responding else None
    guard = check_backend_not_serving(repo_root, backend_responding=responding, identity=identity)
    if guard.blocked:
        raise SystemExit(f"ERROR: {guard.reason}")


