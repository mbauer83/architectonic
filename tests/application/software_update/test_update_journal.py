"""The journal advances one phase at a time, round-trips through its mapping, and refuses another version's."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.application.software_update.installation import BackendObservation, DependencySelection
from src.application.software_update.journal import (
    FIRST_WRITING_PHASE,
    HANDOVER_PHASE,
    JOURNAL_FORMAT,
    PHASE_ORDER,
    JournalInvalid,
    PreviousState,
    TargetRelease,
    UpdateJournal,
)
from src.application.software_update.outcome import EXIT_BY_OUTCOME, classify_outcome


def _journal(phase: str = "planned") -> UpdateJournal:
    return UpdateJournal(
        format=JOURNAL_FORMAT, started_at="2026-10-02T10:00:00Z",
        previous=PreviousState(
            version="0.10.0", commit="abc123", branch="main",
            backend=BackendObservation(True, 4242, 8000, True, ("--admin-mode",)),
            store_held_open=True,
        ),
        target=TargetRelease("0.10.1", "v0.10.1", "def456", "architectonic-gui-0.10.1.tar.gz"),
        selection=DependencySelection(("gui", "dev"), ()), checkout_move="fast_forward", gui="from_release",
        phase=phase, resume_command=("uv", "run", "arch-update", "--resume"),  # type: ignore[arg-type]
    )


def test_the_phases_verify_first_and_write_only_after_planning() -> None:
    assert PHASE_ORDER[0] == "planned"
    assert PHASE_ORDER[1] == FIRST_WRITING_PHASE == "backend_stopped"
    assert PHASE_ORDER.index(HANDOVER_PHASE) == 3


def test_advancing_follows_the_order_and_nothing_else() -> None:
    journal = _journal()
    for phase in PHASE_ORDER[1:]:
        journal = journal.advance(phase)
    assert journal.complete
    with pytest.raises(JournalInvalid):
        _journal().advance("checkout_moved")
    with pytest.raises(JournalInvalid):
        _journal("verified").advance("planned")


@given(st.integers(min_value=0, max_value=len(PHASE_ORDER) - 1))
def test_the_reversal_lists_the_writing_phases_reached_latest_first(index: int) -> None:
    journal = _journal(PHASE_ORDER[index])
    reversal = journal.phases_to_reverse()
    writing = PHASE_ORDER[PHASE_ORDER.index(FIRST_WRITING_PHASE):]
    assert list(reversal) == [phase for phase in reversed(writing) if PHASE_ORDER.index(phase) <= index]


def test_the_mapping_round_trips_including_tuples() -> None:
    journal = _journal("environment_synced")
    assert UpdateJournal.from_mapping(journal.to_mapping()) == journal
    assert journal.handed_over


def test_another_format_or_an_unknown_phase_is_refused_by_name() -> None:
    with pytest.raises(JournalInvalid):
        UpdateJournal.from_mapping({**_journal().to_mapping(), "format": 99})
    with pytest.raises(JournalInvalid):
        UpdateJournal.from_mapping({**_journal().to_mapping(), "phase": "half-done"})
    with pytest.raises(JournalInvalid):
        UpdateJournal.from_mapping({"format": JOURNAL_FORMAT, "phase": "planned"})


def test_outcomes_and_their_exit_codes() -> None:
    assert classify_outcome(_journal("verified"), failed=False, rolled_back=None) == "updated"
    assert classify_outcome(_journal("migrated"), failed=True, rolled_back=True) == "blocked"
    assert classify_outcome(_journal("migrated"), failed=True, rolled_back=False) == "partial"
    assert EXIT_BY_OUTCOME == {"up_to_date": 0, "updated": 0, "blocked": 3, "partial": 20, "infrastructure_failure": 21}
