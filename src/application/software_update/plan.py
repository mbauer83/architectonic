"""Deciding what an update would do, from what was observed and verified (pure).

Observations are supplied by the caller and the plan is a value the caller executes, so every state
an installation can be in is reachable in a test without a socket, a git repository or a release.
A refusal is a value too, and carries the remedy: an operator who is told "no" and nothing else is
left to guess, and guessing is what an updater exists to remove.
"""

from __future__ import annotations

from src.application.software_update import plan_steps
from src.application.software_update.decisions import (  # re-exported: importers name the planner, not the types' file
    CredentialKind,
    CredentialQuestion,
    PlanningResult,
    RehearsalVerdict,
    ReleaseVerification,
    SignatureVerdict,
    UpdatePlan,
    UpdateRefused,
    UpdateStep,
    UpToDate,
)
from src.application.software_update.installation import (
    CheckoutMove,
    CheckoutRelation,
    GuiProvisioning,
    InstallationObservation,
)
from src.application.software_update.release import PublishedRelease

__all__ = [
    "CredentialKind",
    "CredentialQuestion",
    "PlanningResult",
    "RehearsalVerdict",
    "ReleaseVerification",
    "SignatureVerdict",
    "UpdatePlan",
    "UpdateRefused",
    "UpdateStep",
    "UpToDate",
    "plan_update",
]


def plan_update(  # noqa: PLR0911 — a decision table reads as its rows
    observation: InstallationObservation,
    release: PublishedRelease,
    verification: ReleaseVerification,
    rehearsal: RehearsalVerdict | None,
    *,
    gui_source: GuiProvisioning | None = None,
    current_branch_is_main: bool = True,
    relation: CheckoutRelation | None = None,
) -> PlanningResult:
    software = observation.software
    if software.version is not None and release.version <= software.version:
        return UpToDate(software.version)

    move: CheckoutMove = "fast_forward" if current_branch_is_main else "detach"
    refused = _refusal(observation, release, verification, rehearsal) or _checkout_refusal(
        observation, release, move, relation,
    )
    if refused is not None:
        return refused

    gui = gui_source or plan_steps.gui_provisioning(observation, release)
    restart = observation.backend.running
    authorize = observation.store.held_open and observation.store.policy == "manual"
    return UpdatePlan(
        release.version, move, gui,
        plan_steps.steps(observation, release, move, gui, restart, authorize),
        plan_steps.questions(observation),
        (*plan_steps.notes(observation, gui, verification), *_configuration_notes(observation, relation)),
        restart, authorize,
    )


def _refusal(
    observation: InstallationObservation,
    release: PublishedRelease,
    verification: ReleaseVerification,
    rehearsal: RehearsalVerdict | None,
) -> UpdateRefused | None:
    kind = observation.kind
    if kind == "container":
        return UpdateRefused(
            "this process runs inside the container image, which cannot move to another version",
            f"run `arch-update` on the host, in the checkout the image was built from, to move to {release.version}",
            "infrastructure_failure",
        )
    if kind == "remote-attached":
        return UpdateRefused(
            "this checkout is attached to a backend it does not run (ARCH_MCP_BACKEND_URL)",
            "run `arch-update` where that backend runs",
            "infrastructure_failure",
        )
    if kind == "ambiguous":
        return UpdateRefused(
            "this checkout both serves a local backend and runs a compose project",
            "say which deployment is meant: `--deployment local` or `--deployment compose`",
            "blocked",
        )
    if not observation.tooling.uv:
        return UpdateRefused(
            "`uv` is not on PATH, and the environment is synced with it",
            "install uv and re-run",
            "infrastructure_failure",
        )
    if not verification.commit_matches:
        return UpdateRefused(
            f"the fetched tag {release.tag} does not name the commit the release states ({release.commit[:12]})",
            "nothing was installed; check the remote and the release, then re-run",
            "infrastructure_failure",
        )
    if verification.signature in ("unsigned", "untrusted") and observation.software.signers_file_present:
        return UpdateRefused(
            f"tag {release.tag} is {verification.signature} against the installed release-signers file",
            "a release tag must be signed by a key this installation trusts; adding a key is a reviewed change to "
            "`.github/release-signers`",
            "infrastructure_failure",
        )
    failed_assets = [a for a in verification.assets if not a.ok]
    if failed_assets:
        first = failed_assets[0]
        return UpdateRefused(
            f"asset {first.asset}: {first.detail}",
            "nothing was installed; the release's assets do not match what it states",
            "infrastructure_failure",
        )
    if not observation.software.clean:
        listed = ", ".join(observation.software.modified_tracked[:5])
        return UpdateRefused(
            f"the checkout has modified tracked files ({listed})",
            "commit them to a branch of your own or discard them; a modified software checkout is a "
            "developer's to move. The deployment's own configuration (arch-workspace.yaml, "
            "config/settings.yaml) is not counted: it stays as uncommitted edits and is carried across",
            "blocked",
        )
    if observation.backend.unhealthy:
        return UpdateRefused(
            f"this workspace's backend (pid {observation.backend.pid}) is suspended or not answering",
            "run `arch-backend --stop` and re-run",
            "blocked",
        )
    if observation.backend.running and observation.backend.detached is False:
        return UpdateRefused(
            f"this workspace's backend (pid {observation.backend.pid}) is serving in the foreground of a terminal",
            "stop it there, or restart it with `arch-backend --restart --daemon`, then re-run; a foreground process "
            "cannot be put back the way it was",
            "blocked",
        )
    if rehearsal is not None and not rehearsal.clear:
        if rehearsal.could_not_run:
            return UpdateRefused(
                f"{release.version}'s data upgrade could not be rehearsed here: {'; '.join(rehearsal.errors[:3])}",
                "fix what the rehearsal reports and re-run; `--no-rehearse` updates without it, so the live "
                "migration is then the first attempt",
                "blocked",
            )
        what = rehearsal.blocking or rehearsal.uninspectable or rehearsal.errors
        return UpdateRefused(
            f"{release.version}'s data upgrade would not apply cleanly here: {'; '.join(what[:3])}",
            "resolve the findings the rehearsal names (see `arch-repair upgrade`'s report), then re-run",
            "blocked",
        )
    if not observation.interactive and plan_steps.questions(observation):
        envs = ", ".join(question.env_name for question in plan_steps.questions(observation))
        return UpdateRefused(
            "the restart would need a credential and there is no terminal to ask for it",
            f"set {envs} and re-run, or run interactively",
            "infrastructure_failure",
        )
    return None


def _checkout_refusal(
    observation: InstallationObservation,
    release: PublishedRelease,
    move: CheckoutMove,
    relation: CheckoutRelation | None,
) -> UpdateRefused | None:
    """Refuse in the dry run what the move phase would fail on, with the step that resolves it."""
    hidden = observation.software.hidden_configuration
    if hidden:
        listed = " ".join(hidden)
        return UpdateRefused(
            f"git is told to ignore changes to {', '.join(hidden)}, so their edits cannot be carried across",
            # Two commands: `update-index` applies only the last of several marking options it is given.
            f"clear the flags with `git update-index --no-skip-worktree {listed}` and "
            f"`git update-index --no-assume-unchanged {listed}`, then re-run",
            "blocked",
        )
    if relation is None:
        return None
    if move == "fast_forward" and not relation.fast_forwardable:
        base = (relation.merge_base or "the release's ancestor")[:12]
        return UpdateRefused(
            f"`main` has {relation.local_commits} commit(s) that {release.tag} does not contain, so it cannot "
            "fast-forward",
            f"if they hold deployment configuration, turn them back into uncommitted edits with "
            f"`git reset --mixed {base}` (an update carries those across); otherwise move them to a branch of "
            "your own and reset `main` to that commit",
            "blocked",
        )
    if relation.configuration_conflicts:
        listed = ", ".join(relation.configuration_conflicts)
        paths = " ".join(relation.configuration_conflicts)
        return UpdateRefused(
            f"{release.tag} changes {listed}, and the local edits to it conflict with that change",
            f"see the release's change with `git diff HEAD {release.tag} -- {paths}`, "
            "rework your edits so they touch other lines, and re-run",
            "blocked",
        )
    return None


def _configuration_notes(
    observation: InstallationObservation, relation: CheckoutRelation | None,
) -> tuple[str, ...]:
    kept = observation.software.local_configuration
    if not kept:
        return ()
    carried = relation.configuration_changed if relation is not None else ()
    notes = [f"keeps the local configuration edits to {', '.join(kept)}"]
    if carried:
        notes.append(f"the release also changes {', '.join(carried)}: the local edits are merged onto its version")
    return tuple(notes)
