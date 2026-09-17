"""What the planner decides with and decides: verifications, verdicts, questions, steps, a plan or a refusal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.application.software_update.installation import CheckoutMove, GuiProvisioning
from src.application.software_update.release import AssetVerification
from src.application.software_update.version import ReleaseVersion

SignatureVerdict = Literal["verified", "unsigned", "untrusted", "not_enforced"]

@dataclass(frozen=True)
class ReleaseVerification:
    """What checking the fetched tag and the downloaded assets against the release found."""

    #: The fetched tag's commit equals the commit the release names.
    commit_matches: bool
    signature: SignatureVerdict
    assets: tuple[AssetVerification, ...]
    provenance: Literal["verified", "not_verified"]
    provenance_detail: str = ""


@dataclass(frozen=True)
class RehearsalVerdict:
    """The next version's `arch-repair upgrade` dry run over this deployment, summarised."""

    repositories: int
    operational_targets: int
    auto_migratable: int
    blocking: tuple[str, ...]
    uninspectable: tuple[str, ...]
    errors: tuple[str, ...]

    @classmethod
    def not_run(cls, reason: str) -> RehearsalVerdict:
        """A rehearsal that never produced a report: nothing inspected, one error saying why."""
        return cls(
            repositories=0, operational_targets=0, auto_migratable=0, blocking=(), uninspectable=(), errors=(reason,),
        )

    @property
    def could_not_run(self) -> bool:
        return not self.repositories and not self.operational_targets and bool(self.errors)

    @property
    def clear(self) -> bool:
        return not (self.blocking or self.uninspectable or self.errors)


CredentialKind = Literal["git", "vault_master_password"]


@dataclass(frozen=True)
class CredentialQuestion:
    kind: CredentialKind
    what: str
    why: str
    env_name: str


@dataclass(frozen=True)
class UpdateStep:
    key: str
    description: str


@dataclass(frozen=True)
class UpdatePlan:
    target: ReleaseVersion
    checkout_move: CheckoutMove
    gui: GuiProvisioning
    steps: tuple[UpdateStep, ...]
    questions: tuple[CredentialQuestion, ...]
    notes: tuple[str, ...]
    restart_backend: bool
    authorize_store: bool


@dataclass(frozen=True)
class UpdateRefused:
    reason: str
    remedy: str
    #: `blocked` when the installation stays as it is by choice; `infrastructure_failure` when the
    #: release itself could not be trusted or reached.
    outcome: Literal["blocked", "infrastructure_failure"]


@dataclass(frozen=True)
class UpToDate:
    installed: ReleaseVersion


PlanningResult = UpdatePlan | UpdateRefused | UpToDate
