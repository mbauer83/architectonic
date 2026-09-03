"""A submission's phase round-trips, and cannot be constructed in a state that did not happen.

A submission is not one transaction: the push updates a remote nobody can roll back, and it happens
before local state is persisted. So the intent is written down first and the outcome derived after,
by comparing the remote ref against the commit the submission expected. Everything below is about
the two ways that goes wrong — a record that cannot be read back, and a record that claims a step it
never reached.

Stated over what the encoding **permits** rather than what the writer emits today, because a reader
and a writer that disagree here mean a review branch on the remote that nothing local reconciles.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.submission_phase import (
    PREPARED,
    PUSHED,
    SUBMITTED,
    UNRESOLVED,
    CompletedSubmission,
    ImpossibleSubmission,
    PreparedSubmission,
    PushedSubmission,
    SubmissionIntent,
    submission_from_mapping,
)

_ids = st.lists(st.text(min_size=1, max_size=8).filter(str.strip), min_size=1, max_size=4, unique=True)
_intents = st.builds(
    SubmissionIntent,
    proposal_ids=_ids.map(tuple),
    branch=st.text(min_size=1, max_size=20).filter(str.strip),
    expected_commit=st.text(min_size=1, max_size=40).filter(str.strip),
)
_stamps = st.just("2026-09-03T10:00:00Z")


@st.composite
def _phases(draw):
    intent = draw(_intents)
    prepared = PreparedSubmission(intent=intent)
    return draw(st.sampled_from([
        prepared,
        prepared.pushed(at=draw(_stamps)),
        prepared.pushed(at=draw(_stamps)).submitted(at=draw(_stamps)),
    ]))


@settings(max_examples=200, deadline=None)
@given(_phases())
def test_every_permitted_phase_survives_the_round_trip(phase) -> None:
    assert submission_from_mapping(phase.to_mapping()) == phase


def test_all_three_arms_are_reachable_from_the_generator() -> None:
    """Precondition: a strategy producing one arm would make the property above vacuous."""
    intent = _intent()
    prepared = PreparedSubmission(intent=intent)
    reached = {
        type(prepared),
        type(prepared.pushed(at="t")),
        type(prepared.pushed(at="t").submitted(at="t2")),
    }
    assert reached == {PreparedSubmission, PushedSubmission, CompletedSubmission}


def test_the_phases_encode_to_distinct_names() -> None:
    intent = _intent()
    prepared = PreparedSubmission(intent=intent)
    assert prepared.to_mapping()["phase"] == PREPARED
    assert prepared.pushed(at="t").to_mapping()["phase"] == PUSHED
    assert prepared.pushed(at="t").submitted(at="t2").to_mapping()["phase"] == SUBMITTED


class TestWhatCannotBeConstructed:
    def test_a_submission_of_nothing(self) -> None:
        with pytest.raises(ImpossibleSubmission, match="at least one"):
            SubmissionIntent(proposal_ids=(), branch="arch/work-1", expected_commit="abc")

    def test_a_submission_naming_a_change_twice(self) -> None:
        """Replay follows this order, so a repeat applies the same edit twice."""
        with pytest.raises(ImpossibleSubmission, match="twice"):
            SubmissionIntent(proposal_ids=("PCH@1.a", "PCH@1.a"), branch="b", expected_commit="abc")

    @pytest.mark.parametrize("branch", ["", "   ", "\t"])
    def test_a_submission_with_no_branch(self, branch) -> None:
        with pytest.raises(ImpossibleSubmission, match="branch"):
            SubmissionIntent(proposal_ids=("PCH@1.a",), branch=branch, expected_commit="abc")

    @pytest.mark.parametrize("commit", ["", "  "])
    def test_a_submission_with_no_expected_commit(self, commit) -> None:
        """Without one, a retry cannot tell a completed push from a branch someone else moved."""
        with pytest.raises(ImpossibleSubmission, match="expects on the remote"):
            SubmissionIntent(proposal_ids=("PCH@1.a",), branch="b", expected_commit=commit)


class TestWhatCannotBeReadBack:
    @pytest.mark.parametrize("phase", [None, "", "in-flight", "Prepared", "done"])
    def test_an_unrecognised_phase_is_refused_rather_than_read_as_prepared(self, phase) -> None:
        """`prepared` is the tempting default, and it would re-push a submission already in review."""
        with pytest.raises(ImpossibleSubmission):
            submission_from_mapping({**_encoded(), "phase": phase})

    def test_a_pushed_record_with_no_push_stamp(self) -> None:
        with pytest.raises(ImpossibleSubmission, match="pushed_at"):
            submission_from_mapping({**_encoded(), "phase": PUSHED})

    def test_a_submitted_record_with_no_submission_stamp(self) -> None:
        with pytest.raises(ImpossibleSubmission, match="submitted_at"):
            submission_from_mapping({**_encoded(), "phase": SUBMITTED, "pushed_at": "t"})

    @pytest.mark.parametrize("ids", ["PCH@1.a", 7, None, {"a": 1}])
    def test_change_ids_that_are_not_an_ordered_list(self, ids) -> None:
        """A string would iterate character by character and a mapping has no order at all."""
        with pytest.raises(ImpossibleSubmission, match="ordered list"):
            submission_from_mapping({**_encoded(), "proposal_ids": ids})


def test_the_recorded_order_is_the_order_read_back() -> None:
    """Ordering is recorded, not inferred: the same submission must replay identically anywhere."""
    ordered = ("PCH@1.c", "PCH@1.a", "PCH@1.b")
    phase = PreparedSubmission(intent=SubmissionIntent(ordered, "arch/work-1", "abc"))

    decoded = submission_from_mapping(phase.to_mapping())

    assert decoded.intent.proposal_ids == ordered


def test_only_the_unfinished_phases_are_named_for_reconciliation() -> None:
    """A completed submission is settled. Reconciling one would re-decide it against a moved remote."""
    assert set(UNRESOLVED) == {PREPARED, PUSHED}
    assert SUBMITTED not in UNRESOLVED


def _intent() -> SubmissionIntent:
    return SubmissionIntent(proposal_ids=("PCH@1.a",), branch="arch/work-1", expected_commit="abc123")


def _encoded() -> dict:
    return dict(PreparedSubmission(intent=_intent()).to_mapping())
