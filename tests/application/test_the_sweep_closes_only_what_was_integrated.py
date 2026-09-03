"""Which submitted changes a sweep closes, and which it must leave alone.

The sweep runs where the enterprise repository has just moved — at startup, and after the watcher
fetches. Closing a change is destructive in one direction: the author stops seeing it as pending and
stops being offered a rebase for it. So the cases below are mostly about what must *not* be closed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.modeling.integration_sweep import sweep_integrated_changes
from src.application.modeling.proposed_change import (
    BASE_REVISION,
    PROPOSAL_STATE,
    PROPOSED_CHANGE_TYPE,
    PROPOSES_CHANGE_TO,
    RECORDED_EDIT,
    STATES,
)
from src.domain.ontology_representation.artifact_types import EntityRecord

TARGET = "APP@1780000000.aaaaaaa.payments-service"


def _record(artifact_id: str, artifact_type: str, *, name="Payments", extra=None, content="") -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        name=name,
        version="0.1.0",
        status="draft",
        domain="application",
        subdomain=artifact_type,
        path=Path(f"/repo/model/x/{artifact_id}.md"),
        keywords=(),
        extra=extra or {},
        content_text=content,
        display_blocks={},
        display_label=name,
        display_alias="x",
    )


def _proposal(proposal_id: str, *, state="submitted", fields=None, target=TARGET) -> EntityRecord:
    return _record(
        proposal_id,
        PROPOSED_CHANGE_TYPE,
        extra={
            PROPOSES_CHANGE_TO: target,
            PROPOSAL_STATE: state,
            BASE_REVISION: "abc1234",
            RECORDED_EDIT: {
                "kind": "entity",
                "artifact-id": target,
                "fields": fields if fields is not None else {"name": "Payments Platform"},
            },
        },
    )


def _target(name: str) -> EntityRecord:
    return _record(TARGET, "application-component", name=name, content=f"## {name}\n\nx\n\n## Properties\n\n")


@pytest.fixture()
def closer():
    """Records which proposals the sweep asked to close."""
    asked: list[str] = []

    def close(proposal: EntityRecord) -> bool:
        asked.append(proposal.artifact_id)
        return True

    close.asked = asked  # type: ignore[attr-defined]
    return close


def test_a_change_the_artifact_now_carries_is_closed(closer) -> None:
    report = sweep_integrated_changes(
        [_proposal("PCH@1.a")],
        target_of=lambda _id: _target("Payments Platform"),
        close=closer,
    )

    assert closer.asked == ["PCH@1.a"]
    assert [c.proposal_id for c in report.closed] == ["PCH@1.a"]
    assert report.changed_anything


def test_a_change_still_awaiting_review_is_left_open(closer) -> None:
    report = sweep_integrated_changes(
        [_proposal("PCH@1.a")], target_of=lambda _id: _target("Payments"), close=closer
    )

    assert closer.asked == []
    assert [c.proposal_id for c in report.left_open] == ["PCH@1.a"]
    assert report.left_open[0].verdict.differing == ("name",)


@pytest.mark.parametrize("state", [s for s in STATES if s != "submitted"])
def test_only_a_submitted_change_is_swept(state, closer) -> None:
    """A draft has been sent to nobody, so a matching artifact is a coincidence — and closing it
    would delete work the author never submitted. Terminal states are not revisited."""
    report = sweep_integrated_changes(
        [_proposal("PCH@1.a", state=state)],
        target_of=lambda _id: _target("Payments Platform"),
        close=closer,
    )

    assert closer.asked == []
    assert report.closed == () and report.left_open == ()


def test_a_target_that_cannot_be_read_leaves_the_change_open(closer) -> None:
    """An unmounted enterprise repository is missing evidence, not evidence of integration."""
    report = sweep_integrated_changes(
        [_proposal("PCH@1.a")], target_of=lambda _id: None, close=closer
    )

    assert closer.asked == []
    assert report.left_open[0].verdict.undecidable == ("name",)


def test_a_malformed_change_does_not_stop_the_sweep(closer) -> None:
    """The verifier already refuses these with a code. A sweep that raised would stop reconciling
    every other change behind the bad one."""
    broken = _proposal("PCH@1.bad", fields={"nonsense": "x"})
    sound = _proposal("PCH@1.ok")

    report = sweep_integrated_changes(
        [broken, sound], target_of=lambda _id: _target("Payments Platform"), close=closer
    )

    assert closer.asked == ["PCH@1.ok"]
    assert [c.proposal_id for c in report.closed] == ["PCH@1.ok"]


def test_a_change_naming_no_target_is_skipped(closer) -> None:
    report = sweep_integrated_changes(
        [_proposal("PCH@1.a", target="")], target_of=lambda _id: _target("Payments Platform"), close=closer
    )

    assert closer.asked == []
    assert report.closed == ()


def test_records_that_are_not_proposals_are_ignored(closer) -> None:
    report = sweep_integrated_changes(
        [_target("Payments")], target_of=lambda _id: _target("Payments"), close=closer
    )

    assert closer.asked == []
    assert report.summary() == "no submitted changes to reconcile"


def test_a_close_the_writer_declines_is_reported_as_still_open() -> None:
    """The writer answers False when the file was already in that state. The sweep must not claim a
    closure it did not make, or a report would count the same change on every boot."""
    report = sweep_integrated_changes(
        [_proposal("PCH@1.a")],
        target_of=lambda _id: _target("Payments Platform"),
        close=lambda _p: False,
    )

    assert report.closed == ()
    assert [c.proposal_id for c in report.left_open] == ["PCH@1.a"]


def test_the_summary_says_what_happened(closer) -> None:
    report = sweep_integrated_changes(
        [_proposal("PCH@1.a"), _proposal("PCH@1.b", fields={"name": "Something Else"})],
        target_of=lambda _id: _target("Payments Platform"),
        close=closer,
    )

    assert "closed 1" in report.summary()
    assert "1 still awaiting review" in report.summary()
