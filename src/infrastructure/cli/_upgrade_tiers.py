"""Which repositories an upgrade may write, and how it records what it wrote.

**A repository's format is changed by whoever owns it** (B81). A deployment owns its engagement
repository and pushes it; it does not own its enterprise mirror — that tier is maintained upstream,
and the deployment only pulls it. Upgrading the mirror in place left the migration in its working
tree (``--commit`` means "write", not "git commit"), so the next ``arch-init`` refused the dirty clone
and a container could not start a second time. Committing it instead would put the mirror ahead of its
remote, and sync would then block it as diverged.

Measured before deciding (2026-10-26): a backend serves a mirror at the old format identically — 1,225
REST reads compared, the only difference a date stamp on two re-stamped artifacts — so the mirror does
not need migrating to be read. Hence: the enterprise tier is **evaluated and reported, never written**,
unless the deployment says it owns that tier, with the same ``--admin-mode`` the backend takes for
enterprise writes.

What *is* written is recorded as one recognisable commit where that is unambiguous: the repository is
its own top level (a deployment's clone, not a directory inside a development checkout) and its tree
was clean before the upgrade wrote, so the commit holds nothing but the upgrade's output. Otherwise the
files are left written and the report says why — the operator's own changes are never folded into it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from src.application.repository_upgrade.registry import StepRegistry
from src.application.repository_upgrade.workspace import RepoUpgradeTarget, evaluate_workspace
from src.infrastructure.git.git_repository_state import has_uncommitted_changes, is_repository_top_level
from src.infrastructure.git.git_work_commits import commit_format_upgrade
from src.infrastructure.repository_upgrade.fs_adapter import (
    FilesystemRepoUpgradeView,
    FilesystemRepoUpgradeWriter,
)
from src.infrastructure.workspace.workspace_init import load_init_state


@dataclass(frozen=True, slots=True)
class UpgradeRoots:
    """The roots an upgrade writes, and the enterprise roots it only reads and reports."""

    written: tuple[Path, ...]
    owned_upstream: tuple[Path, ...]


def classify_roots(
    *, repo_roots: list[Path], enterprise_roots: list[Path], admin_mode: bool
) -> UpgradeRoots:
    """Every named repository root is written; an enterprise root only where this deployment owns it."""
    written = list(dict.fromkeys(repo_roots))
    upstream: list[Path] = []
    for root in dict.fromkeys(enterprise_roots):
        if root in written:
            continue
        (written if admin_mode else upstream).append(root)
    return UpgradeRoots(written=tuple(written), owned_upstream=tuple(upstream))


def resolve_repo_roots(
    *, repo_root: list[str], workspace: str | None, enterprise_root: list[str] | None = None,
    allow_empty: bool = False,
) -> tuple[list[Path], list[Path]]:
    """The named repository roots, and the enterprise tiers — kept apart, because only one is ours."""
    roots = [Path(p).resolve() for p in repo_root]
    enterprise = [Path(p).resolve() for p in enterprise_root or []]
    if workspace is not None:
        state = load_init_state(Path(workspace).resolve())
        if state is None:
            raise SystemExit(f"ERROR: no arch-init state found under {workspace}")
        roots.append(Path(state["engagement_root"]).resolve())
        enterprise.append(Path(state["enterprise_root"]).resolve())
    if not roots and not enterprise and not allow_empty:
        raise SystemExit("ERROR: specify --repo-root (repeatable) and/or --workspace")
    return list(dict.fromkeys(roots)), list(dict.fromkeys(enterprise))


def report_tiers_left_alone(
    tiers: UpgradeRoots, *, registry: StepRegistry, software_version: str
) -> list[RepoUpgradeTarget]:
    """Evaluate each enterprise tier this run does not write, report it, and return its read-only views.

    The views are returned because the canonical-id join still reads every tier: an operational step
    resolving how an artifact is spelled now must see the enterprise copy whether or not it is written.
    """
    upstream = [
        RepoUpgradeTarget(FilesystemRepoUpgradeView(r), FilesystemRepoUpgradeWriter(r)) for r in tiers.owned_upstream
    ]
    report = evaluate_workspace(upstream, registry=registry, software_version=software_version)
    for root, repo_report in zip(tiers.owned_upstream, report.per_repo, strict=True):
        report_owned_upstream(root, sum(1 for result in repo_report.results if result.finding.auto_migratable))
    return upstream


def report_owned_upstream(root: Path, pending: int) -> None:
    """Say that an enterprise tier was left alone, and how its owner upgrades it — never skip silently."""
    if pending == 0:
        print(f"  enterprise tier {root}: current", file=sys.stderr)
        return
    print(
        f"  enterprise tier {root}: {pending} upgrade finding(s) left unapplied — this deployment does not "
        "own the enterprise tier, so its format is changed upstream: run `arch-repair upgrade --commit "
        "--repo-root <the enterprise repository>` where it is maintained and push, or pass --admin-mode "
        "where this deployment does own it. A backend reads the older format correctly meanwhile.",
        file=sys.stderr,
    )


def clean_before_writing(roots: tuple[Path, ...]) -> dict[Path, bool]:
    """Which roots had a clean tree before the upgrade wrote — read before, because it decides after."""
    return {root: is_repository_top_level(root) and not has_uncommitted_changes(root) for root in roots}


def record_format_upgrade(root: Path, *, clean_before: bool, software_version: str) -> None:
    """Commit what the upgrade wrote to *root* where that is unambiguous; otherwise say why it is left."""
    if not is_repository_top_level(root):
        print(f"  {root}: upgrade left uncommitted — it is not its own repository", file=sys.stderr)
        return
    if not clean_before:
        print(
            f"  {root}: upgrade left uncommitted — the tree already had changes, which a format commit "
            "must not carry; review and commit them together",
            file=sys.stderr,
        )
        return
    if not has_uncommitted_changes(root):
        return
    commit = commit_format_upgrade(
        root, f"Upgrade the persisted repository format (arch-repair upgrade, software {software_version})"
    )
    print(f"  {root}: format upgrade committed as {commit[:7]}", file=sys.stderr)
