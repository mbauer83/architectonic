"""What an installation is observed to be, in the vocabulary the update planner decides over.

Everything here is supplied by an adapter and consumed by `plan_update`; nothing here reads a file
or asks a process. That is what lets every state a machine can be in — a backend serving in the
foreground, a store open under a manual policy, a checkout inside a container — be reached in a test
without one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.application.software_update.version import ReleaseVersion

#: How the software is deployed here. An observation, never a setting: `ambiguous` is a checkout
#: that both serves a local backend and runs a compose project, which the planner refuses to guess at.
DeploymentKind = Literal["local-checkout", "compose-host", "container", "remote-attached", "ambiguous"]

#: How the served GUI bundle is brought to the new version.
GuiProvisioning = Literal["from_release", "build_locally", "leave_stale", "in_image"]

#: How the checkout reaches the release tag.
CheckoutMove = Literal["fast_forward", "detach"]

StorePolicy = Literal["manual", "persistent"]


@dataclass(frozen=True)
class InstalledSoftware:
    """The checkout as it stands."""

    version: ReleaseVersion | None
    commit: str
    branch: str | None
    #: Tracked files with local modifications, `.arch/` excluded. Empty is what "clean" means here;
    #: untracked files are allowed and are not listed.
    modified_tracked: tuple[str, ...]
    #: Whether this version carries an allowed-signers file — the moment one exists, an unsigned tag
    #: is refused.
    signers_file_present: bool
    gui_stamp: str | None
    plantuml_version: str | None

    @property
    def clean(self) -> bool:
        return not self.modified_tracked


@dataclass(frozen=True)
class DependencySelection:
    """The `uv sync` groups and extras the environment has, derived so the next sync reproduces it."""

    groups: tuple[str, ...]
    extras: tuple[str, ...]

    def sync_arguments(self) -> tuple[str, ...]:
        args: list[str] = ["--frozen"]
        for group in self.groups:
            args += ["--group", group]
        for extra in self.extras:
            args += ["--extra", extra]
        return tuple(args)


@dataclass(frozen=True)
class BackendObservation:
    """This workspace's backend, as `backend_control` reports it."""

    running: bool
    pid: int | None
    port: int | None
    #: True when its output is the log or /dev/null, False when a terminal holds it, None when it is
    #: not running or cannot be told.
    detached: bool | None
    #: The serving flags to carry across a restart: `--admin-mode`, `--read-only`, `--host X`.
    flags: tuple[str, ...]
    #: Whether a process is wedged (suspended or unhealthy), which no restart should paper over.
    unhealthy: bool = False


@dataclass(frozen=True)
class StoreObservation:
    """The confidential store's activation state, for deciding whether a restart needs a human."""

    configured: bool
    held_open: bool
    policy: StorePolicy | None
    #: Whether the key can be read without prompting; None when nobody asked.
    key_readable: bool | None
    #: The environment variable that would supply the missing credential, when one is missing.
    missing_credential_env: str | None = None


@dataclass(frozen=True)
class Tooling:
    uv: bool
    npm: bool
    gh: bool
    docker: bool


@dataclass(frozen=True)
class InstallationObservation:
    kind: DeploymentKind
    software: InstalledSoftware
    selection: DependencySelection
    backend: BackendObservation
    store: StoreObservation
    #: Repositories whose git remote needs a credential no environment variable supplies.
    remotes_needing_credentials: tuple[str, ...]
    tooling: Tooling
    interactive: bool
