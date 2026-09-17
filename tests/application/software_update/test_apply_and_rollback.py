"""The phase runner records before it acts, and the rollback reverses what was reached or begun."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.application.software_update.apply import PhaseFailed, run_phases
from src.application.software_update.installation import BackendObservation, DependencySelection
from src.application.software_update.journal import HANDOVER_PHASE, PreviousState, TargetRelease, UpdateJournal
from src.application.software_update.ports import MigrationResult
from src.application.software_update.rollback import roll_back


@dataclass
class RecordingActions:
    fail_at: str | None = None
    fail_reversal: str | None = None
    calls: list[str] = field(default_factory=list)

    def _note(self, name: str) -> None:
        self.calls.append(name)
        if name == self.fail_at or name == self.fail_reversal:
            raise RuntimeError(f"{name} broke")

    def stop_backend(self, port):  # noqa: ANN001, ANN201
        self._note("stop_backend")

    def start_backend(self, previous):  # noqa: ANN001, ANN201
        self._note("start_backend")

    def move_checkout(self, tag, move):  # noqa: ANN001, ANN201
        self._note(f"move_checkout:{tag}:{move}")

    def restore_checkout(self, commit, branch):  # noqa: ANN001, ANN201
        self._note(f"restore_checkout:{commit}:{branch}")

    def sync_environment(self, selection):  # noqa: ANN001, ANN201
        self._note("sync_environment")

    def install_gui(self, gui, target):  # noqa: ANN001, ANN201
        self._note(f"install_gui:{gui}")

    def restore_gui(self):  # noqa: ANN201
        self._note("restore_gui")

    def reconcile_assets(self):  # noqa: ANN201
        self._note("reconcile_assets")
        return ("plantuml.jar re-pinned",)

    def migrate(self):  # noqa: ANN201
        self._note("migrate")
        return MigrationResult(checkpoint_set="20261002T090000Z", committed=True)

    def restore_checkpoint(self, checkpoint_set):  # noqa: ANN001, ANN201
        self._note(f"restore_checkpoint:{checkpoint_set}")

    def authorize_store(self):  # noqa: ANN201
        self._note("authorize_store")

    def verify(self, target, *, backend_expected):  # noqa: ANN001, ANN201
        self._note("verify")


class MemoryStore:
    def __init__(self) -> None:
        self.writes: list[UpdateJournal] = []
        self.archived: list[str] = []

    def read(self) -> UpdateJournal | None:
        return self.writes[-1] if self.writes else None

    def write(self, journal: UpdateJournal) -> None:
        self.writes.append(journal)

    def archive(self, journal: UpdateJournal, outcome: str) -> None:
        self.archived.append(outcome)


def _journal(*, running: bool = True, store_open: bool = True) -> UpdateJournal:
    return UpdateJournal(
        format=1, started_at="2026-10-02T09:00:00Z",
        previous=PreviousState(
            "0.10.0", "abc1234def", "main", BackendObservation(running, 42, 8000, True, ()), store_open,
        ),
        target=TargetRelease("0.10.1", "v0.10.1", "def4567abc", "architectonic-gui-0.10.1.tar.gz"),
        selection=DependencySelection(("gui",), ()), checkout_move="fast_forward", gui="from_release",
        phase="planned", resume_command=("uv", "run", "arch-update", "--resume"),
    )


def test_the_installed_version_runs_to_the_handover_and_records_each_phase_before_and_after() -> None:
    actions, store = RecordingActions(), MemoryStore()

    journal = run_phases(_journal(), actions, store, through=HANDOVER_PHASE)

    assert journal.phase == "environment_synced" and journal.in_flight is None and journal.handed_over
    assert actions.calls == ["stop_backend", "move_checkout:v0.10.1:fast_forward", "sync_environment"]
    written = [(j.phase, j.in_flight) for j in store.writes]
    assert written[:2] == [("planned", "backend_stopped"), ("backend_stopped", None)]


def test_the_new_version_resumes_from_the_handover_to_verified() -> None:
    actions, store = RecordingActions(), MemoryStore()
    handed_over = run_phases(_journal(), RecordingActions(), MemoryStore(), through=HANDOVER_PHASE)

    journal = run_phases(handed_over, actions, store, through="verified")

    assert journal.complete and journal.checkpoint_set == "20261002T090000Z" and journal.migration_committed
    assert "plantuml.jar re-pinned" in journal.notes
    assert actions.calls == [
        "install_gui:from_release", "reconcile_assets", "migrate", "start_backend", "authorize_store", "verify",
    ]


def test_a_backend_that_was_not_running_is_neither_stopped_nor_started() -> None:
    actions = RecordingActions()

    run_phases(_journal(running=False, store_open=False), actions, MemoryStore(), through="verified")

    assert "stop_backend" not in actions.calls and "start_backend" not in actions.calls
    assert "authorize_store" not in actions.calls


def test_a_failing_phase_leaves_the_journal_naming_it_in_flight() -> None:
    actions, store = RecordingActions(fail_at="migrate"), MemoryStore()
    handed_over = run_phases(_journal(), RecordingActions(), MemoryStore(), through=HANDOVER_PHASE)

    with pytest.raises(PhaseFailed) as failure:
        run_phases(handed_over, actions, store, through="verified")

    assert failure.value.phase == "migrated" and "migrate broke" in str(failure.value)
    assert failure.value.journal.in_flight == "migrated" and failure.value.journal.phase == "assets_reconciled"
    assert store.read() is not None and store.read().in_flight == "migrated"


@pytest.mark.verifies("REQ@1789640735.7Qke86l")
def test_a_rollback_after_a_committed_migration_restores_data_then_software_then_processes() -> None:
    actions = RecordingActions()
    journal = run_phases(_journal(), RecordingActions(), MemoryStore(), through="backend_started")
    journal = journal.begin("store_authorized")

    result = roll_back(journal, actions, MemoryStore())

    assert result.complete
    assert actions.calls == [
        "stop_backend",
        "restore_checkpoint:20261002T090000Z",
        "restore_gui",
        "restore_checkout:abc1234def:main",
        "sync_environment",
        "reconcile_assets",
        "start_backend",
        "authorize_store",
    ]


def test_a_rollback_before_the_checkout_moved_only_restarts_the_backend() -> None:
    actions = RecordingActions()
    journal = _journal().advance("backend_stopped").begin("checkout_moved")

    result = roll_back(journal, actions, MemoryStore())

    assert result.complete
    # The move may have half-happened, so the checkout is put back even though the phase never completed.
    assert actions.calls == [
        "restore_checkout:abc1234def:main", "sync_environment", "start_backend", "authorize_store",
    ]


def test_a_migration_interrupted_before_its_report_is_named_as_unresolved() -> None:
    journal = run_phases(_journal(), RecordingActions(), MemoryStore(), through="assets_reconciled").begin("migrated")

    result = roll_back(journal, RecordingActions(), MemoryStore())

    assert not result.complete and "--list-checkpoints" in result.remaining[0]


def test_a_reversal_that_fails_is_reported_and_the_rest_still_run() -> None:
    actions = RecordingActions(fail_reversal="restore_gui")
    journal = run_phases(_journal(), RecordingActions(), MemoryStore(), through="gui_installed")

    result = roll_back(journal, actions, MemoryStore())

    assert result.remaining == ("restore the previous GUI bundle: restore_gui broke",)
    assert "start_backend" in actions.calls and "restore_checkout:abc1234def:main" in actions.calls
