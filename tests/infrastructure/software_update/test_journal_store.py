"""The journal file survives a process boundary, and the lock refuses a second live updater only."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.application.software_update.installation import BackendObservation, DependencySelection
from src.application.software_update.journal import PreviousState, TargetRelease, UpdateJournal
from src.infrastructure.software_update.journal_store import FileJournalStore, UpdateInProgress


def _journal() -> UpdateJournal:
    return UpdateJournal(
        format=1, started_at="2026-10-02T09:00:00Z",
        previous=PreviousState(
            "0.10.0", "abc1234def", "main", BackendObservation(True, 42, 8000, True, ("--admin-mode",)), True,
        ),
        target=TargetRelease("0.10.1", "v0.10.1", "def4567abc", None),
        selection=DependencySelection(("gui", "dev"), ("s3-archive",)),
        checkout_move="fast_forward", gui="build_locally",
        phase="planned", resume_command=("uv", "run", "arch-update", "--resume"),
    )


def test_a_written_journal_reads_back_equal_through_each_phase(tmp_path: Path) -> None:
    store = FileJournalStore(tmp_path)
    journal = _journal().advance("backend_stopped").begin("checkout_moved")

    store.write(journal)

    assert store.read() == journal
    assert store.read().previous.backend.flags == ("--admin-mode",)


def test_archiving_retires_the_journal_into_the_history_with_its_outcome(tmp_path: Path) -> None:
    store = FileJournalStore(tmp_path)
    store.write(_journal())

    store.archive(_journal(), "updated")

    assert store.read() is None
    assert store.last_archived()["outcome"] == "updated"
    assert list(store.history.glob("*-0.10.1-updated.json"))


def test_the_lock_is_re_entered_by_its_own_pid_and_refused_to_a_live_other(tmp_path: Path) -> None:
    store = FileJournalStore(tmp_path)
    store.acquire()
    store.acquire()  # the resumed new version has the same pid after execv
    assert store.lock_holder() == os.getpid()

    other = FileJournalStore(tmp_path)
    other.lock_path.write_text(str(os.getppid()))  # a live process that is not us
    with pytest.raises(UpdateInProgress):
        other.acquire()


def test_a_lock_left_by_a_dead_process_is_taken_over(tmp_path: Path) -> None:
    store = FileJournalStore(tmp_path)
    store.directory.mkdir(parents=True)
    store.lock_path.write_text("999999999")

    store.acquire()

    assert store.lock_holder() == os.getpid()
    store.release()
    assert not store.lock_path.exists()
