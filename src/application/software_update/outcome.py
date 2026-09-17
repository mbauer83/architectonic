"""How an update ended, and the exit status that says so — the same table `arch-repair upgrade` uses."""

from __future__ import annotations

from typing import Literal

from src.application.software_update.journal import UpdateJournal

UpdateOutcome = Literal["up_to_date", "updated", "blocked", "partial", "infrastructure_failure"]

EXIT_BY_OUTCOME: dict[UpdateOutcome, int] = {
    "up_to_date": 0,
    "updated": 0,
    #: Refused, or rolled back completely: the installation is as it was.
    "blocked": 3,
    #: A phase failed and the rollback could not undo everything; the journal says what remains.
    "partial": 20,
    #: A failure before anything changed: network, a digest that did not match, a refused signature,
    #: a credential missing without a terminal to ask.
    "infrastructure_failure": 21,
}


def classify_outcome(journal: UpdateJournal, *, failed: bool, rolled_back: bool | None) -> UpdateOutcome:
    """`updated` when verified; `blocked` when everything was put back; `partial` when a rollback left
    something. A failure before any journal exists is `infrastructure_failure`, decided where it happens."""
    if journal.complete and not failed:
        return "updated"
    if rolled_back is True:
        return "blocked"
    return "partial"
