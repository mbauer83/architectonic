"""Attempt the next version's data upgrade in a throwaway checkout before the live one moves.

A worktree at the release tag gets its own environment from the same lock, and *that* version's
`arch-repair upgrade` runs its dry run over the live deployment's repositories and operational
targets. The dry run is read-only and permitted while a backend serves, so the whole question
"would this update's data upgrade apply cleanly here" is answered with nothing stopped and nothing
written. The worktree is removed however the block exits; `prune_stale_worktrees` covers a kill.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from src.application.software_update.installation import DependencySelection
from src.application.software_update.plan import RehearsalVerdict
from src.domain.repository.operational_upgrade import REPORT_SCHEMA_VERSION
from src.infrastructure.git.rehearsal_worktree import RehearsalUnavailable, rehearsal_worktree
from src.infrastructure.software_update._commands import CommandFailed, checkout_tool, run_checked

#: The report contract this reader understands; a newer version's report is refused rather than
#: half-read, because a verdict built from misread findings would let an update through.
KNOWN_REPORT_SCHEMA_VERSIONS = frozenset({REPORT_SCHEMA_VERSION})

_SYNC_TIMEOUT_SECONDS = 1800
_DRY_RUN_TIMEOUT_SECONDS = 1800


class RehearsalFailed(RuntimeError):
    """The rehearsal could not be run — the worktree, the sync or the dry run itself failed."""


def rehearse(
    root: Path,
    *,
    start_point: str,
    selection: DependencySelection,
    upgrade_arguments: Sequence[str],
    uv: str = "uv",
) -> RehearsalVerdict:
    """Run `start_point`'s `arch-repair upgrade` dry run with `upgrade_arguments`, from a worktree."""
    try:
        with rehearsal_worktree(root, start_point=start_point) as rehearsal:
            run_checked(
                [uv, "sync", *selection.sync_arguments()],
                cwd=rehearsal.path, timeout=_SYNC_TIMEOUT_SECONDS, doing="syncing the rehearsal environment",
            )
            # A dry run always exits 0 (its findings are report states); anything else is the tool failing.
            stdout = run_checked(
                checkout_tool(uv, rehearsal.path, "arch-repair", "upgrade", "--json", *upgrade_arguments),
                cwd=rehearsal.path, timeout=_DRY_RUN_TIMEOUT_SECONDS, doing="dry-running the data upgrade",
            )
    except (RehearsalUnavailable, CommandFailed) as exc:
        raise RehearsalFailed(str(exc)) from exc
    try:
        report = json.loads(stdout)
    except ValueError as exc:
        raise RehearsalFailed(f"the dry run did not answer with a JSON report: {stdout[:200]!r}") from exc
    return verdict_from_report(report)


def verdict_from_report(report: Mapping[str, object]) -> RehearsalVerdict:
    """Summarise a `--json` upgrade report the way the planner decides over it."""
    version = str(report.get("report_schema_version"))
    if version not in KNOWN_REPORT_SCHEMA_VERSIONS:
        raise RehearsalFailed(f"the dry run's report schema {version!r} is not one this version reads")
    repos = _mappings(report.get("repos"))
    targets = _mappings(report.get("operational_targets"))
    findings = [
        (f"{item.get('repo_root', '?')}: ", finding) for item in repos for finding in _mappings(item.get("findings"))
    ] + [
        (f"{target.get('kind', '?')}: ", finding) for target in targets for finding in _mappings(target.get("findings"))
    ]
    blocking = tuple(f"{where}{f.get('finding_id')}" for where, f in findings if f.get("blocks_commit"))
    errors = tuple(f"{where}{f.get('finding_id')}" for where, f in findings if f.get("outcome") == "error")
    uninspectable = tuple(str(target.get("kind")) for target in targets if target.get("state") == "uninspectable")
    return RehearsalVerdict(
        repositories=len(repos),
        operational_targets=len(targets),
        auto_migratable=sum(1 for _, f in findings if f.get("auto_migratable")),
        blocking=blocking,
        uninspectable=uninspectable,
        errors=errors,
    )


def _mappings(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
