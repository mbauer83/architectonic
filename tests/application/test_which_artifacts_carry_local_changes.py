"""What the resolver answers, and what it refuses to guess.

The read side of a proposal: given the proposal records in a repository, which artifacts differ from
the enterprise baseline, and in which fields. The cases below are the decisions this resolver makes
that a reader would otherwise have to guess at — several proposals against one artifact, a terminal
one, one that does not decode, and a revision that cannot be taken.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.modeling.proposal_standing import (
    PendingProposal,
    pending_proposals,
    standing_for,
)
from src.application.modeling.proposed_change import (
    BASE_REVISION,
    PROPOSAL_STATE,
    PROPOSED_CHANGE_TYPE,
    PROPOSES_CHANGE_TO,
    RECORDED_EDIT,
    STATES,
)
from src.domain.baseline_standing import BASELINE, EnterpriseBaseline, Proposed
from src.domain.ontology_representation.artifact_types import EntityRecord

TARGET = "APP@1780000000.aaaaaaa.payments-service"
OTHER = "APP@1780000000.bbbbbbb.billing-service"
REVISION = "0f1e2d3c4b5a6978"


def _proposal(
    proposal_id: str,
    *,
    target: str = TARGET,
    fields: dict | None = None,
    state: str = "draft",
    base: str = REVISION,
    kind: str = "entity",
) -> EntityRecord:
    return EntityRecord(
        artifact_id=proposal_id,
        artifact_type=PROPOSED_CHANGE_TYPE,
        name="a change",
        version="0.1.0",
        status="draft",
        domain="common",
        subdomain="proposed-change",
        path=Path(f"/repo/model/common/proposed-change/{proposal_id}.md"),
        keywords=(),
        extra={
            PROPOSES_CHANGE_TO: target,
            PROPOSAL_STATE: state,
            BASE_REVISION: base,
            RECORDED_EDIT: {
                "kind": kind,
                "artifact-id": target,
                "fields": fields if fields is not None else {"summary": "a better summary"},
            },
        },
        content_text="",
        display_blocks={},
        display_label="a change",
        display_alias="a_change",
    )


def _unchanged(_: str) -> str | None:
    return REVISION


def _moved(_: str) -> str | None:
    return "9999999999999999"


def _unreadable(_: str) -> str | None:
    return None


def test_an_artifact_with_nothing_against_it_is_the_baseline() -> None:
    assert standing_for(TARGET, {}, revision_of=_unchanged) is BASELINE
    assert isinstance(standing_for(TARGET, {}, revision_of=_unchanged), EnterpriseBaseline)


def test_an_artifact_with_a_live_change_says_which_field() -> None:
    pending = pending_proposals([_proposal("PCH@1.aaa", fields={"summary": "x"})])
    standing = standing_for(TARGET, pending, revision_of=_unchanged)

    assert isinstance(standing, Proposed)
    assert standing.changed_fields == ("summary",)
    assert standing.proposal_ids == ("PCH@1.aaa",)
    assert standing.condition == "current"


def test_changes_against_a_different_artifact_do_not_reach_this_one() -> None:
    pending = pending_proposals([_proposal("PCH@1.aaa", target=OTHER)])

    assert standing_for(TARGET, pending, revision_of=_unchanged) is BASELINE
    assert isinstance(standing_for(OTHER, pending, revision_of=_unchanged), Proposed)


def test_several_changes_against_one_artifact_report_the_union_of_their_fields() -> None:
    """Two changes against one artifact are ordinary. A reader asking which parts are local wants
    both answers, not whichever was written first."""
    pending = pending_proposals([
        _proposal("PCH@1.bbb", fields={"summary": "x"}),
        _proposal("PCH@1.aaa", fields={"name": "y", "status": "accepted"}),
    ])
    standing = standing_for(TARGET, pending, revision_of=_unchanged)

    assert isinstance(standing, Proposed)
    assert standing.changed_fields == ("name", "status", "summary")
    assert standing.proposal_ids == ("PCH@1.aaa", "PCH@1.bbb")


def test_the_report_does_not_depend_on_the_order_records_arrive_in() -> None:
    """Filesystem order is not a fact about the model, and a standing that changed with it would make
    two readers of the same repository disagree."""
    one, two = _proposal("PCH@1.bbb", fields={"name": "y"}), _proposal("PCH@1.aaa", fields={"status": "z"})

    forwards = standing_for(TARGET, pending_proposals([one, two]), revision_of=_unchanged)
    backwards = standing_for(TARGET, pending_proposals([two, one]), revision_of=_unchanged)

    assert forwards == backwards


@pytest.mark.parametrize("state", ["integrated", "abandoned"])
def test_a_terminal_change_is_no_longer_a_local_difference(state) -> None:
    """An integrated change *is* the baseline now, and an abandoned one never will be."""
    pending = pending_proposals([_proposal("PCH@1.aaa", state=state)])

    assert pending == {}
    assert standing_for(TARGET, pending, revision_of=_unchanged) is BASELINE


@pytest.mark.parametrize("state", ["draft", "submitted"])
def test_a_live_change_is_a_local_difference_in_every_live_state(state) -> None:
    pending = pending_proposals([_proposal("PCH@1.aaa", state=state)])

    assert isinstance(standing_for(TARGET, pending, revision_of=_unchanged), Proposed)


def test_every_declared_state_is_decided_one_way_or_the_other() -> None:
    """Enumerating a closed set and getting it wrong is the failure this pins: a state added to the
    vocabulary and forgotten here would silently stop reporting its changes."""
    decided = {
        state: bool(pending_proposals([_proposal("PCH@1.aaa", state=state)]))
        for state in STATES
    }

    assert decided == {"draft": True, "submitted": True, "integrated": False, "abandoned": False}


def test_a_change_whose_base_the_enterprise_has_moved_past_is_stale() -> None:
    pending = pending_proposals([_proposal("PCH@1.aaa")])
    standing = standing_for(TARGET, pending, revision_of=_moved)

    assert isinstance(standing, Proposed)
    assert standing.condition == "stale"


def test_one_stale_change_among_several_makes_the_artifact_stale() -> None:
    pending = pending_proposals([
        _proposal("PCH@1.aaa", base=REVISION),
        _proposal("PCH@1.bbb", base="1111111111111111"),
    ])

    assert standing_for(TARGET, pending, revision_of=_unchanged).condition == "stale"


def test_a_revision_that_cannot_be_taken_does_not_report_stale() -> None:
    """An unmounted enterprise repository is missing evidence, not evidence of movement. Guessing the
    alarming direction costs an author a rebase they did not need."""
    pending = pending_proposals([_proposal("PCH@1.aaa")])

    assert standing_for(TARGET, pending, revision_of=_unreadable).condition == "current"


def test_conflicting_is_not_produced_here() -> None:
    """It is the outcome of rehearsing a rebase, which is a later milestone. A second, cheaper meaning
    invented here is how one word comes to mean two things in one system."""
    combinations = [
        standing_for(TARGET, pending_proposals([_proposal("PCH@1.aaa", fields={"name": "x"}),
                                               _proposal("PCH@1.bbb", fields={"name": "y"})]),
                     revision_of=reader)
        for reader in (_unchanged, _moved, _unreadable)
    ]

    assert all(s.condition in ("current", "stale") for s in combinations)


@pytest.mark.parametrize(
    "broken",
    [
        {PROPOSES_CHANGE_TO: ""},
        {PROPOSES_CHANGE_TO: None},
        {BASE_REVISION: ""},
        {BASE_REVISION: 17},
        {RECORDED_EDIT: "not a mapping"},
        {RECORDED_EDIT: {"kind": "connection", "artifact-id": TARGET, "fields": {"summary": "x"}}},
        {RECORDED_EDIT: {"kind": "entity", "artifact-id": TARGET, "fields": {}}},
        {RECORDED_EDIT: {"kind": "entity", "artifact-id": TARGET, "fields": {"nonsense": "x"}}},
        {RECORDED_EDIT: {"artifact-id": TARGET, "fields": {"summary": "x"}}},
        {PROPOSAL_STATE: "invented"},
        {PROPOSAL_STATE: ""},
    ],
)
def test_a_change_that_does_not_decode_is_left_out_rather_than_raised_on(broken) -> None:
    """The verifier refuses these with a code and a message. A read path that raised would take a whole
    page down over one malformed file and hide every other artifact's standing behind it."""
    record = _proposal("PCH@1.aaa")
    damaged = EntityRecord(**{**record.__dict__, "extra": {**record.extra, **broken}})

    assert pending_proposals([damaged]) == {}
    assert standing_for(TARGET, pending_proposals([damaged]), revision_of=_unchanged) is BASELINE


def test_a_malformed_change_does_not_hide_a_sound_one_against_the_same_artifact() -> None:
    """The reason the refusal is per-record rather than per-call."""
    sound = _proposal("PCH@1.aaa", fields={"summary": "x"})
    broken = EntityRecord(**{**sound.__dict__, "artifact_id": "PCH@1.bad",
                             "extra": {**sound.extra, BASE_REVISION: ""}})

    standing = standing_for(TARGET, pending_proposals([broken, sound]), revision_of=_unchanged)

    assert isinstance(standing, Proposed)
    assert standing.proposal_ids == ("PCH@1.aaa",)


def test_records_that_are_not_proposals_are_not_read_as_ones() -> None:
    ordinary = EntityRecord(**{**_proposal("APP@1.aaa").__dict__, "artifact_type": "application-component"})

    assert pending_proposals([ordinary]) == {}


def test_a_pending_proposal_carries_only_what_a_reader_of_its_target_needs() -> None:
    """The reduced shape is the point: a read path holding whole proposal records would carry their
    bodies through every list answer."""
    (proposal,) = pending_proposals([_proposal("PCH@1.aaa", fields={"name": "y"})])[TARGET]

    assert proposal == PendingProposal("PCH@1.aaa", TARGET, ("name",), REVISION)
