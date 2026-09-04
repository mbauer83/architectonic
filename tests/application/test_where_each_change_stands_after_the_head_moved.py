"""The three positions a pending change can be in once the enterprise artifact has moved on.

The plan's red-first cases, in order: a change whose target moved in a section it does not name
replays clean; one the enterprise already satisfied reports **superseded**, not conflict; one that no
longer verifies reports the verifier's own refusal and changes nothing.

The second is why integration detection had to be built first. Reporting an already-accepted change
as a conflict asks an author to resolve their own merged work, which is the single most confusing
thing a rebase can say.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.modeling.change_rebase import REBASE_OUTCOMES, rehearse_rebase
from src.application.modeling.proposal_edit import ProposalEdit
from src.domain.ontology_representation.artifact_types import EntityRecord

TARGET = "APP@1780000000.aaaaaaa.payments-service"
REFUSAL = "E012 'status' must be one of draft, accepted, superseded"


def _target(*, name="Payments", summary="Handles payments.", status="draft") -> EntityRecord:
    return EntityRecord(
        artifact_id=TARGET,
        artifact_type="application-component",
        name=name,
        version="0.1.0",
        status=status,
        domain="application",
        subdomain="application-component",
        path=Path("/repo/model/application/application-component/payments.md"),
        keywords=(),
        extra={},
        content_text=f"## {name}\n\n{summary}\n\n## Properties\n\n## Notes\n\n",
        display_blocks={},
        display_label=name,
        display_alias="payments",
    )


def _edit(**fields) -> ProposalEdit:
    return ProposalEdit(kind="entity", artifact_id=TARGET, fields=fields)


def _applies(_edit_: ProposalEdit) -> str | None:
    return None


def _refuses(_edit_: ProposalEdit) -> str | None:
    return REFUSAL


class TestTheThreePositions:
    def test_a_change_replays_clean_when_the_target_moved_elsewhere(self) -> None:
        """A change names fields, so a section it does not name cannot conflict with it — the
        property the recorded-edit representation was chosen for."""
        moved_elsewhere = _target(name="Payments", summary="Rewritten by someone else entirely.")

        rehearsed = rehearse_rebase(
            [("PCH@1.a", _edit(name="Payments Platform"))],
            target_of=lambda _id: moved_elsewhere,
            replay=_applies,
        )

        assert [c.outcome for c in rehearsed.changes] == ["clean"]
        assert rehearsed.can_proceed

    def test_a_change_the_enterprise_already_satisfied_is_superseded(self) -> None:
        """Not a conflict. Reporting one would ask an author to resolve their own accepted work."""
        already = _target(name="Payments Platform")

        rehearsed = rehearse_rebase(
            [("PCH@1.a", _edit(name="Payments Platform"))],
            target_of=lambda _id: already,
            replay=_refuses,  # never reached: nothing is replayed for a superseded change
        )

        (change,) = rehearsed.changes
        assert change.outcome == "superseded"
        assert "already says" in change.reason

    def test_a_change_that_no_longer_verifies_carries_the_refusal_verbatim(self) -> None:
        """The verifier's own words: they are what the author acts on, and a second wording here
        would be a second vocabulary for one refusal."""
        rehearsed = rehearse_rebase(
            [("PCH@1.a", _edit(status="retired"))], target_of=lambda _id: _target(), replay=_refuses
        )

        (change,) = rehearsed.changes
        assert change.outcome == "conflicting"
        assert change.reason == REFUSAL
        assert not rehearsed.can_proceed


class TestTheEdges:
    def test_a_target_that_is_gone_conflicts_rather_than_replaying(self) -> None:
        rehearsed = rehearse_rebase(
            [("PCH@1.a", _edit(name="Payments Platform"))], target_of=lambda _id: None, replay=_applies
        )

        (change,) = rehearsed.changes
        assert change.outcome == "conflicting"
        assert "not in the enterprise repository" in change.reason

    def test_a_superseded_change_is_never_replayed(self) -> None:
        """Replaying one would write what is already there, and could fail for reasons that are not
        the author's problem."""
        attempted: list[str] = []

        def record(edit: ProposalEdit) -> str | None:
            attempted.append(edit.artifact_id)
            return None

        rehearse_rebase(
            [("PCH@1.a", _edit(name="Payments Platform"))],
            target_of=lambda _id: _target(name="Payments Platform"),
            replay=record,
        )

        assert attempted == []

    def test_the_submitted_order_is_preserved(self) -> None:
        """Replay order is part of the submission's command; a report that reordered it would not
        describe what a later replay does."""
        rehearsed = rehearse_rebase(
            [
                ("PCH@1.c", _edit(name="Third")),
                ("PCH@1.a", _edit(summary="First")),
                ("PCH@1.b", _edit(status="accepted")),
            ],
            target_of=lambda _id: _target(),
            replay=_applies,
        )

        assert [c.proposal_id for c in rehearsed.changes] == ["PCH@1.c", "PCH@1.a", "PCH@1.b"]


class TestWhetherToOpenAReplacementBranch:
    def test_not_while_anything_conflicts(self) -> None:
        rehearsed = rehearse_rebase(
            [("PCH@1.a", _edit(name="A")), ("PCH@1.b", _edit(status="x"))],
            target_of=lambda _id: _target(),
            replay=lambda edit: REFUSAL if "status" in edit.fields else None,
        )

        assert not rehearsed.can_proceed
        assert len(rehearsed.with_outcome("clean")) == 1

    def test_not_when_everything_is_already_upstream(self) -> None:
        """A branch carrying nothing is a change for a reviewer to puzzle over."""
        rehearsed = rehearse_rebase(
            [("PCH@1.a", _edit(name="Payments Platform"))],
            target_of=lambda _id: _target(name="Payments Platform"),
            replay=_applies,
        )

        assert rehearsed.with_outcome("superseded")
        assert not rehearsed.can_proceed

    def test_yes_when_something_is_clean_and_nothing_conflicts(self) -> None:
        rehearsed = rehearse_rebase(
            [("PCH@1.a", _edit(name="Payments Platform")), ("PCH@1.b", _edit(summary="New."))],
            target_of=lambda _id: _target(),
            replay=_applies,
        )

        assert rehearsed.can_proceed


def test_the_summary_counts_every_declared_outcome() -> None:
    """Enumerating a closed set and getting it wrong is a failure this project has paid for twice."""
    rehearsed = rehearse_rebase(
        [
            ("PCH@1.a", _edit(name="Payments Platform")),
            ("PCH@1.b", _edit(summary="New.")),
            ("PCH@1.c", _edit(status="x")),
        ],
        target_of=lambda _id: _target(name="Payments Platform"),
        replay=lambda edit: REFUSAL if "status" in edit.fields else None,
    )

    assert set(REBASE_OUTCOMES) == {"clean", "superseded", "conflicting"}
    assert rehearsed.summary() == "1 clean, 1 already upstream, 1 conflicting"


@pytest.mark.parametrize("outcome", REBASE_OUTCOMES)
def test_every_outcome_is_reachable(outcome) -> None:
    """A classification with an unreachable arm is a rule nothing exercises."""
    rehearsed = rehearse_rebase(
        [
            ("PCH@1.a", _edit(name="Payments Platform")),
            ("PCH@1.b", _edit(summary="New.")),
            ("PCH@1.c", _edit(status="x")),
        ],
        target_of=lambda _id: _target(name="Payments Platform"),
        replay=lambda edit: REFUSAL if "status" in edit.fields else None,
    )

    assert rehearsed.with_outcome(outcome), outcome
