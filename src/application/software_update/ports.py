"""What the update needs from the outside, as ports the composition root supplies.

Each port is one seam an adapter fills and a test stubs: where releases come from, what the checkout
is and how it moves. Nothing here performs I/O; the application functions beside this module compose
the ports into the dry run and, later, the journaled apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.software_update.installation import (
    BackendObservation,
    CheckoutMove,
    DependencySelection,
    GuiProvisioning,
    InstalledSoftware,
)
from src.application.software_update.journal import TargetRelease, UpdateJournal
from src.application.software_update.plan import SignatureVerdict
from src.application.software_update.release import PublishedRelease, ReleaseAsset
from src.application.software_update.version import ReleaseVersion


class ReleaseSourceError(RuntimeError):
    """The release source could not answer — network, rate limit, an unexpected response."""


class ReleaseSource(Protocol):
    """Where published releases are read from."""

    def latest(self, *, include_prerelease: bool) -> PublishedRelease | None:
        """The newest release, or None where the repository has published none."""
        ...

    def by_version(self, version: ReleaseVersion) -> PublishedRelease | None: ...

    def download(self, asset: ReleaseAsset) -> bytes: ...


class Checkout(Protocol):
    """The installation's git checkout: what it is, and how it reaches a release tag."""

    def observe(self) -> InstalledSoftware: ...

    def fetch_tag(self, tag: str) -> str | None:
        """Fetch the tag from the origin and return the commit it names, or None when it is not there."""
        ...

    def verify_tag(self, tag: str) -> SignatureVerdict: ...

    def on_main_branch(self) -> bool: ...


@dataclass(frozen=True)
class MigrationResult:
    """What `arch-repair upgrade --commit` left: its safety point, and whether it wrote anything."""

    checkpoint_set: str | None
    committed: bool


class MigrationIncomplete(RuntimeError):
    """The data upgrade wrote to some targets and stopped; `checkpoint_set` is what a rollback restores."""

    def __init__(self, detail: str, *, checkpoint_set: str | None) -> None:
        super().__init__(detail)
        self.checkpoint_set = checkpoint_set


class UpdateActions(Protocol):
    """The effects one update phase has on a deployment, and how each is undone.

    One implementation per deployment kind. Every method either completes or raises; the phase
    runner records the phase only after the method returns, and the rollback calls the reversals in
    the order `rollback.py` fixes. Reversals are idempotent, because a rollback may follow an action
    that half-happened.
    """

    def stop_backend(self, port: int | None) -> None: ...

    def start_backend(self, previous: BackendObservation) -> None: ...

    def move_checkout(self, tag: str, move: CheckoutMove) -> None: ...

    def restore_checkout(self, commit: str, branch: str | None) -> None: ...

    def sync_environment(self, selection: DependencySelection) -> None: ...

    def install_gui(self, gui: GuiProvisioning, target: TargetRelease) -> None: ...

    def restore_gui(self) -> None: ...

    def reconcile_assets(self) -> tuple[str, ...]:
        """Re-provision the pinned assets of the checkout as it stands now; returns what changed."""
        ...

    def migrate(self) -> MigrationResult: ...

    def restore_checkpoint(self, checkpoint_set: str) -> None: ...

    def authorize_store(self) -> None: ...

    def verify(self, target: TargetRelease, *, backend_expected: bool) -> None:
        """Raise unless the checkout, and the backend when one should serve, report `target`."""
        ...


class JournalStore(Protocol):
    """Where the in-flight journal lives between phases and processes."""

    def read(self) -> UpdateJournal | None: ...

    def write(self, journal: UpdateJournal) -> None: ...

    def archive(self, journal: UpdateJournal, outcome: str) -> None:
        """Move the journal out of the in-flight slot into the history, tagged with how it ended."""
        ...
