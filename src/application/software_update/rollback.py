"""Put an interrupted or failed update back: data first, then software, then the processes.

The order is fixed by what depends on what. The new backend, if it started, is stopped before the
data it may hold open is restored; the data upgrade's checkpoint set is restored while the *new*
software is still the checkout, because only that version can read its own report; then the checkout
returns to the recorded commit and the environment is synced to it; the assets are reconciled again
so the previous pins are what is installed; and last the previous backend is started and the store
re-authorized where it had been open. Every reversal is attempted even when an earlier one failed —
a partial rollback is reported as one, named step by step, never silently abandoned.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.application.software_update.journal import UpdateJournal
from src.application.software_update.ports import JournalStore, UpdateActions


@dataclass(frozen=True)
class RollbackResult:
    restored: tuple[str, ...]
    remaining: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.remaining


def roll_back(journal: UpdateJournal, actions: UpdateActions, store: JournalStore) -> RollbackResult:
    """Reverse what `journal` says was reached or begun; returns what was put back and what was not."""
    previous = journal.previous
    restored: list[str] = []
    remaining: list[str] = []

    def attempt(name: str, action: Callable[[], object]) -> None:
        try:
            action()
        except Exception as exc:  # noqa: BLE001 — recorded, and the next reversal still runs
            remaining.append(f"{name}: {exc}")
        else:
            restored.append(name)

    if journal.touched("backend_started") and previous.backend.running:
        attempt("stop the backend the update started", lambda: actions.stop_backend(previous.backend.port))
    checkpoint = journal.checkpoint_set
    if journal.touched("migrated"):
        if checkpoint is not None:
            attempt(f"restore checkpoint set {checkpoint}", lambda: actions.restore_checkpoint(checkpoint))
        elif journal.in_flight == "migrated":
            remaining.append(
                "the data upgrade was interrupted before it reported; run "
                "`arch-repair upgrade --list-checkpoints` and `--restore` the newest set if one was taken"
            )
    if journal.touched("gui_installed"):
        attempt("restore the previous GUI bundle", actions.restore_gui)
    software_moved = journal.touched("checkout_moved")
    if software_moved:
        attempt(
            f"return the checkout to {previous.commit[:7]}",
            lambda: actions.restore_checkout(previous.commit, previous.branch),
        )
    if software_moved or journal.touched("environment_synced"):
        attempt("sync the environment to the previous version", lambda: actions.sync_environment(journal.selection))
    if journal.touched("assets_reconciled"):
        attempt("re-provision the previous version's pinned assets", actions.reconcile_assets)
    if journal.touched("backend_stopped") and previous.backend.running:
        attempt(f"start the backend on port {previous.backend.port}", lambda: actions.start_backend(previous.backend))
        if previous.store_held_open:
            attempt("re-authorize the assurance store", actions.authorize_store)
    result = RollbackResult(tuple(restored), tuple(remaining))
    store.write(journal)
    return result
