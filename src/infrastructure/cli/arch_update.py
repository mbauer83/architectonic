"""`arch-update`: check what release is published, verify it, and say what an update would do.

Dry run by default, in the shape of `arch-repair upgrade`: nothing is written, the exit status is 0,
and an available update is a report state. `--commit` runs the same check and plan and then the
journaled phases (`_update_commit`); `--resume`, `--rollback` and `--status` act on the journal alone.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from src.application.software_update.evaluate import ReleaseCheck, check_release
from src.application.software_update.installation import GuiProvisioning, InstallationObservation
from src.application.software_update.outcome import EXIT_BY_OUTCOME
from src.application.software_update.plan import (
    PlanningResult,
    RehearsalVerdict,
    UpdatePlan,
    UpdateRefused,
    UpToDate,
    plan_update,
)
from src.application.software_update.ports import ReleaseSourceError
from src.application.software_update.release import PublishedRelease
from src.application.software_update.version import NotAReleaseVersion, parse_release_version
from src.config.settings import update_repository
from src.infrastructure.cli import _update_commit
from src.infrastructure.cli._update_report import render_human, render_json
from src.infrastructure.deployment.layout import source_tree_root
from src.infrastructure.software_update.checkout import CheckoutError, GitCheckout
from src.infrastructure.software_update.github_releases import GitHubReleases, token_from_environment
from src.infrastructure.software_update.observation import deployment_identity_arguments, observe_installation
from src.infrastructure.software_update.rehearsal import RehearsalFailed, rehearse

#: The checkout this command is installed from.
PROJECT_ROOT = source_tree_root()

_GUI_SOURCES: dict[str, GuiProvisioning] = {"release": "from_release", "build": "build_locally"}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="arch-update",
        description="Check the published releases, verify the newest, and report what an update would do.",
    )
    p.add_argument("--to", metavar="VERSION", help="A specific release instead of the newest")
    p.add_argument("--include-prerelease", action="store_true", default=False)
    p.add_argument("--json", action="store_true", default=False, dest="json_output")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--commit", action="store_true", default=False, help="Perform the update the dry run plans")
    mode.add_argument("--resume", action="store_true", default=False, help=argparse.SUPPRESS)
    mode.add_argument("--rollback", action="store_true", default=False, help="Put an in-flight update back")
    mode.add_argument("--status", action="store_true", default=False, help="The update in flight, or the last one")
    p.add_argument(
        "--resolve-selection", action="append", default=[], metavar="SLUG=scope|query",
        help="Passed through to `arch-repair upgrade --commit`",
    )
    p.add_argument("--compose-file", metavar="PATH", type=Path, help="The compose file, when not docker-compose.yml")
    p.add_argument(
        "--deployment", choices=("local", "compose"), default=None,
        help="Which deployment is meant when this checkout both serves a backend and runs a compose project",
    )
    p.add_argument("--repository", metavar="OWNER/REPO", help="Override update.repository from settings")
    p.add_argument(
        "--no-rehearse", action="store_false", dest="rehearse", default=True,
        help="Skip running the release's own `arch-repair upgrade` dry run in a worktree (about half a minute)",
    )
    p.add_argument(
        "--gui-source", choices=("release", "build"), default=None,
        help="Where the served GUI comes from: the release's bundle (default when it has one) or a local npm build",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.status:
        return _update_commit.status(PROJECT_ROOT, json_output=args.json_output)
    if args.rollback:
        return _update_commit.rollback(PROJECT_ROOT, json_output=args.json_output)
    if args.resume:
        return _update_commit.resume(
            PROJECT_ROOT, json_output=args.json_output, resolve_selection=args.resolve_selection,
        )
    try:
        requested = parse_release_version(args.to) if args.to else None
    except NotAReleaseVersion as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    repository = args.repository or update_repository()
    source = GitHubReleases(repository, token=token_from_environment())
    checkout = GitCheckout(PROJECT_ROOT)
    try:
        check = check_release(source, checkout, requested=requested, include_prerelease=args.include_prerelease)
    except (ReleaseSourceError, CheckoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 21
    observation = observe_installation(
        PROJECT_ROOT, check.installed, compose_file=args.compose_file, deployment=args.deployment,
    )
    planning, rehearsal = _planning_for(
        check, observation, gui_source=_gui_source(args.gui_source), on_main=checkout.on_main_branch(),
        rehearse_first=args.rehearse,
    )
    if args.json_output:
        print(render_json(check, planning, rehearsal=rehearsal))
    else:
        print(render_human(check, planning, situation=_situation(observation), rehearsal=rehearsal))
    if not args.commit:
        return 0
    if isinstance(planning, UpdateRefused):
        return EXIT_BY_OUTCOME[planning.outcome]
    if not isinstance(planning, UpdatePlan):
        return 0
    # The phases talk to this workspace's backend and store through helpers that read the cwd.
    os.chdir(PROJECT_ROOT)
    return _update_commit.commit(
        check, observation, planning, root=PROJECT_ROOT, json_output=args.json_output,
        resolve_selection=args.resolve_selection, compose_file=args.compose_file,
    )


def _planning_for(
    check: ReleaseCheck,
    observation: InstallationObservation,
    *,
    gui_source: GuiProvisioning | None,
    on_main: bool,
    rehearse_first: bool,
) -> tuple[PlanningResult | None, RehearsalVerdict | None]:
    """Plan without the rehearsal first, so a refused update never pays for a worktree it will not use."""
    release, verification = check.release, check.verification
    if release is None:
        return None, None
    if not check.update_available and check.installed.version is not None:
        return UpToDate(check.installed.version), None
    if verification is None:
        return None, None

    def plan(rehearsal: RehearsalVerdict | None) -> PlanningResult:
        return plan_update(
            observation, release, verification, rehearsal=rehearsal,
            gui_source=gui_source, current_branch_is_main=on_main,
        )

    preliminary = plan(None)
    if not rehearse_first or not isinstance(preliminary, UpdatePlan):
        return preliminary, None
    verdict = _rehearsed(release, observation)
    return plan(verdict), verdict


def _rehearsed(release: PublishedRelease, observation: InstallationObservation) -> RehearsalVerdict:
    print(f"rehearsing {release.version}'s data upgrade in a worktree at {release.tag} …", file=sys.stderr)
    try:
        return rehearse(
            PROJECT_ROOT, start_point=release.tag, selection=observation.selection,
            upgrade_arguments=deployment_identity_arguments(PROJECT_ROOT),
        )
    except RehearsalFailed as exc:
        return RehearsalVerdict.not_run(str(exc))


def _gui_source(choice: str | None) -> GuiProvisioning | None:
    return None if choice is None else _GUI_SOURCES[choice]


def _situation(observation: InstallationObservation) -> str:
    kind = observation.kind.replace("-", " ")
    backend = observation.backend
    if backend.running:
        how = "detached" if backend.detached else "foreground" if backend.detached is False else "unknown stdio"
        served = f"backend running on {backend.port} (pid {backend.pid}, {how})"
    else:
        served = "backend not running"
    store = observation.store
    if store.configured:
        state = "open" if store.held_open else "locked"
        served += f" · store {state} ({store.policy})"
    return f"{kind} · {served}"


if __name__ == "__main__":
    raise SystemExit(main())
