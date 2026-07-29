"""Per-repository commit phases for `arch-repair upgrade`: classified pre-existing
consistency repair (stale-temp sweep + transaction recovery), the dirty-overlap
note, and report emission. Diagnostics go to stderr; stdout carries only the
human report or JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.domain.repository.operational_upgrade import DeploymentUpgradeReport
from src.domain.repository.repository_upgrade import COVERAGE_NOTE, WorkspaceUpgradeReport
from src.infrastructure.atomic_file import sweep_stale_tmp_files
from src.infrastructure.cli._upgrade_deployment import print_operational_reports
from src.infrastructure.repository_upgrade.fs_adapter import FilesystemRepoUpgradeWriter
from src.infrastructure.repository_upgrade.guard import conflicting_dirty_files
from src.infrastructure.write.artifact_write.m4_transaction import (
    TransactionRecoveryError,
    recover_transactions,
)


def sweep_and_recover(repo_root: Path) -> list[str]:
    """Classified pre-existing consistency repair; returns what it did for the report."""
    repairs: list[str] = []
    # Sweep orphaned atomic-write temp files a previous, killed `upgrade --commit` may have
    # left behind — harmless litter, never a source of truth, safe to remove now that no
    # concurrent writer can be holding one open.
    swept = sweep_stale_tmp_files(repo_root)
    if swept:
        print(
            f"Removed {len(swept)} stale temp file(s) from a previous interrupted run in {repo_root}.",
            file=sys.stderr,
        )
        repairs.append(f"{repo_root}: removed {len(swept)} stale temp file(s)")

    # Idempotent recovery of any transaction a crashed backend left mid-flight, so steps
    # always see a consistent repo regardless of git-sync/promotion history.
    try:
        recovered = recover_transactions(
            repo_root, rebuild_index=FilesystemRepoUpgradeWriter(repo_root).rebuild_index
        )
    except TransactionRecoveryError as exc:
        raise SystemExit(
            f"ERROR: {repo_root} has an unrecoverable pending transaction — resolve manually "
            f"before upgrading: {exc}"
        ) from exc
    if recovered:
        print(f"Recovered {recovered} pending transaction(s) in {repo_root} before upgrading.", file=sys.stderr)
        repairs.append(f"{repo_root}: recovered {recovered} pending transaction(s)")
    return repairs


def note_dirty_overlap(repo_root: Path, touched_locations: frozenset[str]) -> None:
    overlap = conflicting_dirty_files(repo_root, touched_locations)
    if overlap:
        files = "\n".join(f"  {f}" for f in overlap)
        print(
            f"Note: {repo_root} has uncommitted local edits to {len(overlap)} file(s) this "
            f"run will also rewrite — your edits are carried forward, not lost, but review "
            f"the combined diff before committing:\n{files}",
            file=sys.stderr,
        )


def emit_deployment(report: DeploymentUpgradeReport, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return
    print(f"Note: {COVERAGE_NOTE}")
    _print_repos(report.repos)
    print_operational_reports(report.operational_targets)
    preflight = report.preflight
    if preflight is not None:
        for note in preflight.notes:
            print(f"Note: {note}")
        for repair in preflight.pre_existing_repairs:
            print(f"Pre-existing repair (not a migration write): {repair}")


def _print_repos(report: WorkspaceUpgradeReport) -> None:
    for repo_report in report.per_repo:
        print(f"\n{repo_report.repo_root}")
        print(f"  format_contract_version: {repo_report.format_contract_version}")
        print(f"  applied_steps: {', '.join(repo_report.applied_steps_after) or '(none)'}")
        if not repo_report.results:
            print("  no findings")
            continue
        for result in repo_report.results:
            f = result.finding
            print(f"  [{result.outcome}] {f.step_id}/{f.finding_id} ({f.severity}) — {f.location}: {f.description}")
