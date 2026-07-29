"""Deployment-scoped side of `arch-repair upgrade`.

Operational targets (guidance cache, signal stores, the settings document) bind
to an explicit deployment identity — `--settings`, `--deployment-root`, or the
`ARCH_SETTINGS_PATH` process selector. `--workspace` alone keeps its unchanged
repositories-only semantics, so a test workspace can never reach the user's
real global cache or stores. `--exclude-target` is for operator-run partial
commands only; the report then states deployment readiness is NOT certified.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass

from src.application.deployment_upgrade.ports import OperationalTargetHandle
from src.domain.deployment.layout import ENV_SETTINGS_PATH, CliSelectors, DeploymentManifest
from src.domain.repository.operational_upgrade import (
    DeploymentPreflight,
    OperationalTargetReport,
)
from src.domain.repository.repository_upgrade import UpgradeFinding
from src.infrastructure.deployment.discovery import discover_operational_handles
from src.infrastructure.deployment.layout import resolve_manifest

OPERATIONAL_KINDS: tuple[str, ...] = (
    "deployment_settings",
    "guidance_cache",
    "signals_sqlite",
    "assurance_sqlcipher",
)


@dataclass(frozen=True)
class DeploymentSide:
    """Everything the upgrade CLI needs about the operational half of a run."""

    manifest: DeploymentManifest | None
    handles: tuple[OperationalTargetHandle, ...]
    preflight: DeploymentPreflight | None

    @property
    def active(self) -> bool:
        return self.manifest is not None


def add_deployment_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--settings", metavar="PATH", help="Deployment settings document (explicit deployment identity)")
    p.add_argument(
        "--deployment-root", metavar="PATH", help="Deployment root (settings.yaml + default operational paths)"
    )
    p.add_argument("--guidance-cache", metavar="PATH", help="Override the guidance-cache root for this deployment")
    p.add_argument("--signals-db", metavar="PATH", help="Override the public signals SQLite path")
    p.add_argument("--assurance-store", metavar="PATH", help="Override the SQLCipher assurance store path")
    p.add_argument(
        "--exclude-target",
        action="append",
        default=[],
        choices=OPERATIONAL_KINDS,
        metavar="KIND",
        help="Skip one operational target kind (operator-run partial commands only; readiness is then NOT certified)",
    )


def deployment_identity_present(args: argparse.Namespace, env: Mapping[str, str]) -> bool:
    return bool(args.settings or args.deployment_root or env.get(ENV_SETTINGS_PATH))


def build_deployment_side(args: argparse.Namespace, env: Mapping[str, str]) -> DeploymentSide:
    """Phase 1 for operational targets: resolve identity, discover, dedup.

    May raise `DeploymentLayoutConflict` — a hard error before any target is
    opened or created.
    """
    if not deployment_identity_present(args, env):
        return DeploymentSide(manifest=None, handles=(), preflight=None)
    cli = CliSelectors(
        settings=args.settings,
        deployment_root=args.deployment_root,
        workspace=args.workspace,
        assurance_store=args.assurance_store,
        signals_db=args.signals_db,
        guidance_cache=args.guidance_cache,
    )
    manifest = resolve_manifest(cli, env)
    handles = discover_operational_handles(manifest)
    excluded = set(args.exclude_target)
    notes = tuple(manifest.archive_notes)
    if excluded:
        skipped = ", ".join(sorted(excluded))
        notes = (*notes, f"targets excluded by operator: {skipped} — deployment readiness NOT certified")
        handles = tuple(h for h in handles if h.target.kind not in excluded)
    preflight = DeploymentPreflight(
        settings_document=str(manifest.settings_document.path),
        settings_source=manifest.settings_document.source,
        operator_owned=manifest.settings_document.operator_owned,
        notes=notes,
    )
    return DeploymentSide(manifest=manifest, handles=handles, preflight=preflight)


def operational_blocking_findings(
    reports: tuple[OperationalTargetReport, ...],
) -> list[UpgradeFinding]:
    return [
        result.finding
        for report in reports
        for result in report.results
        if result.finding.blocks_commit
    ]


def print_operational_reports(reports: tuple[OperationalTargetReport, ...]) -> None:
    for report in reports:
        target = report.target
        version = "unknown" if target.current_version is None else target.current_version
        configured = "" if target.configured else " (not selected by active configuration)"
        print(f"\n{target.kind} @ {target.display_location}{configured}")
        print(f"  state: {report.state} · version: {version} · committed: {report.committed}")
        if report.detail:
            print(f"  {report.detail}")
        for result in report.results:
            f = result.finding
            print(f"  [{result.outcome}] {f.step_id}/{f.finding_id} ({f.severity}) — {f.description}")
