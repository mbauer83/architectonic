"""The phase runner: one action per phase, the journal written before and after each.

`run_phases` carries a journal from its current phase through `through`, calling the one action a
phase stands for and recording the phase only once the action returned. The record is written
*before* the action too, as the phase in flight, so a process that dies between the action and its
record leaves a journal from which `rollback.py` still knows what may have changed. The re-exec
boundary is a caller's concern: it runs `through=HANDOVER_PHASE`, executes the recorded command, and
the new version runs the rest.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from src.application.software_update.journal import PHASE_ORDER, UpdateJournal, UpdatePhase
from src.application.software_update.ports import JournalStore, MigrationIncomplete, UpdateActions


@dataclass(frozen=True)
class PhaseFailed(Exception):
    """A phase's action raised; `journal` names it in flight, so a rollback can reverse it."""

    journal: UpdateJournal
    phase: UpdatePhase
    error: str

    def __str__(self) -> str:
        return f"{self.phase}: {self.error}"


def run_phases(
    journal: UpdateJournal,
    actions: UpdateActions,
    store: JournalStore,
    *,
    through: UpdatePhase,
    on_phase: Callable[[UpdatePhase], None] | None = None,
) -> UpdateJournal:
    """Run every phase after `journal.phase` up to and including `through`; raise `PhaseFailed` on the first error."""
    stop = PHASE_ORDER.index(through)
    while (phase := journal.next_phase) is not None and PHASE_ORDER.index(phase) <= stop:
        begun = journal.begin(phase)
        store.write(begun)
        if on_phase is not None:
            on_phase(phase)
        try:
            journal = _perform(begun, phase, actions)
        except MigrationIncomplete as exc:
            # The safety point is the one thing a partial migration leaves that a rollback needs.
            begun = replace(begun, checkpoint_set=exc.checkpoint_set, migration_committed=True)
            store.write(begun)
            raise PhaseFailed(begun, phase, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — every failure shape ends the same way: a rollback
            raise PhaseFailed(begun, phase, str(exc) or exc.__class__.__name__) from exc
        journal = journal.advance(phase)
        store.write(journal)
    return journal


def _perform(journal: UpdateJournal, phase: UpdatePhase, actions: UpdateActions) -> UpdateJournal:
    previous = journal.previous
    match phase:
        case "backend_stopped":
            if previous.backend.running:
                actions.stop_backend(previous.backend.port)
        case "checkout_moved":
            actions.move_checkout(journal.target.tag, journal.checkout_move)
        case "environment_synced":
            actions.sync_environment(journal.selection)
        case "gui_installed":
            actions.install_gui(journal.gui, journal.target)
        case "assets_reconciled":
            changed = actions.reconcile_assets()
            if changed:
                journal = replace(journal, notes=(*journal.notes, *changed))
        case "migrated":
            result = actions.migrate()
            journal = replace(journal, checkpoint_set=result.checkpoint_set, migration_committed=result.committed)
        case "backend_started":
            if previous.backend.running:
                actions.start_backend(previous.backend)
        case "store_authorized":
            if previous.store_held_open:
                actions.authorize_store()
        case "verified":
            actions.verify(journal.target, backend_expected=previous.backend.running)
        case "planned":
            raise AssertionError("planned is the journal's starting phase, never run")
    return journal
