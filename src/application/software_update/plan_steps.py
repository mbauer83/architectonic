"""The wording of a plan: which steps an update takes, what it will ask for, and what it notes."""

from __future__ import annotations

from src.application.software_update.decisions import (
    CredentialQuestion,
    ReleaseVerification,
    UpdateStep,
)
from src.application.software_update.installation import CheckoutMove, GuiProvisioning, InstallationObservation
from src.application.software_update.release import PublishedRelease


def gui_provisioning(observation: InstallationObservation, release: PublishedRelease) -> GuiProvisioning:
    if observation.kind == "compose-host":
        return "in_image"
    if release.asset(release.gui_bundle_name) is not None:
        return "from_release"
    return "build_locally" if observation.tooling.npm else "leave_stale"


def questions(observation: InstallationObservation) -> tuple[CredentialQuestion, ...]:
    if observation.kind == "compose-host":
        return ()  # the container reads its credentials from `.env`; nothing is prompted
    questions: list[CredentialQuestion] = []
    if observation.backend.running and observation.remotes_needing_credentials:
        remotes = ", ".join(observation.remotes_needing_credentials)
        questions.append(CredentialQuestion(
            "git", "git credentials", f"the restarted backend syncs {remotes}",
            "ARCH_GIT_SSH_PASSWORD / ARCH_GIT_HTTPS_TOKEN",
        ))
    store = observation.store
    if store.held_open and store.policy == "manual" and store.key_readable is False and store.missing_credential_env:
        questions.append(CredentialQuestion(
            "vault_master_password", "assurance vault master password",
            "the store is open under the manual policy and must be re-authorized",
            store.missing_credential_env,
        ))
    return tuple(questions)


def steps(
    observation: InstallationObservation, release: PublishedRelease, move: CheckoutMove,
    gui: GuiProvisioning, restart: bool, authorize: bool,
) -> tuple[UpdateStep, ...]:
    if observation.kind == "compose-host":
        return compose_steps(observation, release, move)
    port = observation.backend.port
    steps: list[UpdateStep] = []
    if restart:
        steps.append(UpdateStep("stop_backend", f"stop the backend (pid {observation.backend.pid}, port {port})"))
    steps.append(UpdateStep("move_checkout", move_text(release, move)))
    steps.append(UpdateStep("sync_environment", "uv sync " + " ".join(observation.selection.sync_arguments())))
    gui_text = {
        "from_release": f"install the GUI bundle {release.gui_bundle_name} from the release",
        "build_locally": "build the GUI locally (npm ci && npm run build); the release carries no bundle",
        "leave_stale": "leave the served GUI as it is: the release carries no bundle and npm is not on PATH",
        "in_image": "the image carries the GUI",
    }[gui]
    steps.append(UpdateStep("provision_gui", gui_text))
    steps.append(UpdateStep(
        "reconcile_assets", "re-provision plantuml.jar and the embedding model where their pins moved",
    ))
    steps.append(UpdateStep("migrate", "arch-repair upgrade --commit (checkpoints every target first)"))
    if restart:
        flags = " ".join(observation.backend.flags)
        with_flags = f" {flags}" if flags else ""
        steps.append(UpdateStep("start_backend", f"start the backend detached on port {port}{with_flags}"))
    if authorize:
        how = "no prompt" if observation.store.key_readable else "asks for the vault master password first"
        steps.append(UpdateStep("authorize_store", f"authorize the assurance store ({how})"))
    steps.append(UpdateStep("verify", f"verify the served version is {release.version}"))
    return tuple(steps)


def move_text(release: PublishedRelease, move: CheckoutMove) -> str:
    if move == "fast_forward":
        return f"fast-forward the branch to {release.tag}"
    return f"check out {release.tag} detached"


def compose_steps(
    observation: InstallationObservation, release: PublishedRelease, move: CheckoutMove,
) -> tuple[UpdateStep, ...]:
    """D10a: build outside the downtime, stop before the guard-blind migration, migrate inside the new image."""
    port = observation.backend.port
    return (
        UpdateStep("move_checkout", move_text(release, move)),
        UpdateStep(
            "sync_environment",
            "uv sync on the host, anchor the running image as architectonic:"
            f"{observation.software.version}, then docker compose build",
        ),
        UpdateStep("stop_backend", "docker compose stop app"),
        UpdateStep(
            "migrate",
            "docker compose run --rm --no-deps --entrypoint arch-repair app upgrade --commit "
            "(checkpoints every target first, inside the new image)",
        ),
        UpdateStep("start_backend", f"docker compose up -d app, then wait for the container on port {port}"),
        UpdateStep("verify", f"verify the served version is {release.version}"),
    )


def notes(
    observation: InstallationObservation, gui: GuiProvisioning, verification: ReleaseVerification,
) -> tuple[str, ...]:
    notes: list[str] = []
    if verification.signature == "not_enforced":
        notes.append("the tag's signature is not enforced: this installation carries no release-signers file")
    if verification.provenance == "not_verified":
        notes.append(f"provenance: not verified ({verification.provenance_detail or 'gh not on PATH'})")
    if gui == "leave_stale":
        notes.append("the served GUI will lag the backend until `npm run build` is run in tools/gui")
    if observation.backend.running:
        notes.append(
            "MCP stdio bridges started by agent clients keep running the previous version "
            "until the client restarts them"
        )
    return tuple(notes)
