"""One change per artifact, through the whole lifecycle rather than only in a list.

An author who edits a promoted requirement twice has changed it twice; they have not made two
proposals, and a reviewer should not hold two overlapping opinions about one artifact. So a further
edit never adds a change — it replaces the one it finds, and how depends on whether anyone upstream
has been shown it.

The two properties that carry the whole design are asserted last: the union keeps fields the author
never retracted, and the base revision does not move, because superseding is not an event upstream
and staleness is decided by comparing that revision against enterprise HEAD.
"""

from __future__ import annotations

import pytest

from src.application.modeling.change_recording import (
    RecordNew,
    ReviseDraft,
    SupersedeSubmitted,
    UnrecordableChange,
    decide,
)
from src.application.modeling.proposal_edit import ProposalEdit
from src.application.modeling.proposal_standing import PendingProposal

_TARGET = "REQ@1712870400.aaaaaa.two-tier-repositories"
#: How the engagement repository addresses it — what the change file names, since an
#: engagement deployment holds no enterprise content to point at.
_REFERENCE = "GAR@1780000040.aaaaaa.two-tier-repositories"


def _pending(proposal_id: str, state: str, base: str = "rev-1", **fields: object) -> PendingProposal:
    return PendingProposal(
        proposal_id=proposal_id,
        target_id=_TARGET,
        reference_id=_REFERENCE,
        changed_fields=tuple(sorted(fields)),
        base_revision=base,
        state=state,
        edit=ProposalEdit(kind="entity", artifact_id=_TARGET, fields=fields),
    )


def _decide(fields: dict[str, object], pending: list[PendingProposal]):  # noqa: ANN202
    return decide(kind="entity", target_id=_TARGET, fields=fields, pending=pending)


# ── nothing pending ──────────────────────────────────────────────────────────


def test_the_first_edit_becomes_the_artifacts_change() -> None:
    outcome = _decide({"summary": "Mine."}, [])
    assert isinstance(outcome, RecordNew)
    assert outcome.edit.fields == {"summary": "Mine."}
    assert outcome.edit.artifact_id == _TARGET


def test_an_edit_that_changes_nothing_is_refused() -> None:
    with pytest.raises(UnrecordableChange):
        _decide({}, [])


# ── a draft nobody has been shown ────────────────────────────────────────────


def test_a_draft_is_revised_in_place() -> None:
    """It keeps its identity, so a badge's link and a reader's bookmark survive a second thought."""
    outcome = _decide({"summary": "Better."}, [_pending("PC@1", "draft", summary="First.")])
    assert isinstance(outcome, ReviseDraft)
    assert outcome.proposal_id == "PC@1"
    assert outcome.edit.fields == {"summary": "Better."}


def test_revising_a_draft_keeps_fields_the_new_edit_does_not_name() -> None:
    outcome = _decide({"summary": "Better."}, [_pending("PC@1", "draft", summary="First.", notes="Kept.")])
    assert outcome.edit.fields == {"summary": "Better.", "notes": "Kept."}


# ── a submitted change someone is looking at ─────────────────────────────────


def test_a_submitted_change_is_superseded_rather_than_edited() -> None:
    outcome = _decide({"summary": "Second thoughts."}, [_pending("PC@1", "submitted", summary="First.")])
    assert isinstance(outcome, SupersedeSubmitted)
    assert outcome.superseded_ids == ("PC@1",)


def test_the_superseding_change_carries_both_field_sets() -> None:
    """The scenario this design was worked out for: one field overlaps, one is new."""
    outcome = _decide(
        {"summary": "Second thoughts.", "notes": "And a note."},
        [_pending("PC@1", "submitted", summary="First.", keywords=["tiering"])],
    )
    assert outcome.edit.fields == {
        "summary": "Second thoughts.",
        "notes": "And a note.",
        "keywords": ["tiering"],
    }


def test_the_newer_edit_wins_where_they_overlap() -> None:
    outcome = _decide({"summary": "Newer."}, [_pending("PC@1", "submitted", summary="Older.")])
    assert outcome.edit.fields["summary"] == "Newer."


def test_work_the_author_never_retracted_survives() -> None:
    """Dropping the earlier change's other fields would discard work nobody withdrew."""
    outcome = _decide({"summary": "Newer."}, [_pending("PC@1", "submitted", summary="Older.", notes="Untouched.")])
    assert outcome.edit.fields["notes"] == "Untouched."


# ── several live changes, which the stored shape still permits ───────────────


def test_every_live_change_is_superseded_not_just_one() -> None:
    """The only reading of “one change per artifact” that converges on a repository that has more."""
    outcome = _decide(
        {"summary": "Mine."},
        [_pending("PC@1", "submitted", summary="A."), _pending("PC@2", "draft", notes="B.")],
    )
    assert isinstance(outcome, SupersedeSubmitted)
    assert outcome.superseded_ids == ("PC@1", "PC@2")
    assert outcome.edit.fields == {"summary": "Mine.", "notes": "B."}


def test_two_drafts_are_superseded_rather_than_one_revised() -> None:
    """Revising “the” draft would leave the other live, which is the state the rule forbids."""
    outcome = _decide(
        {"summary": "Mine."},
        [_pending("PC@1", "draft", summary="A."), _pending("PC@2", "draft", notes="B.")],
    )
    assert isinstance(outcome, SupersedeSubmitted)


def test_the_outcome_does_not_depend_on_the_order_they_were_gathered_in() -> None:
    first = _pending("PC@1", "submitted", summary="A.")
    second = _pending("PC@2", "submitted", notes="B.")
    assert _decide({"keywords": ["x"]}, [first, second]) == _decide({"keywords": ["x"]}, [second, first])


# ── the two properties the whole design rests on ─────────────────────────────


def test_the_base_revision_does_not_move() -> None:
    """Superseding is not an event upstream. Moving it would mark a stale change current."""
    outcome = _decide({"summary": "Mine."}, [_pending("PC@1", "submitted", base="rev-old", summary="A.")])
    assert isinstance(outcome, SupersedeSubmitted)
    assert outcome.base_revision == "rev-old"


def test_where_bases_disagree_the_oldest_is_carried() -> None:
    """A change claiming a newer base than its oldest content would read as current when part of it
    is not."""
    outcome = _decide(
        {"summary": "Mine."},
        [
            _pending("PC@1", "submitted", base="rev-b", summary="A."),
            _pending("PC@2", "draft", base="rev-a", notes="B."),
        ],
    )
    assert isinstance(outcome, SupersedeSubmitted)
    assert outcome.base_revision == "rev-a"
