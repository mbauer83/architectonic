"""Composing the set of changes one submission carries.

The set is judged before anything is replayed. Every refusal here is one the author reads instead of
a half-written enterprise repository, so the tests are about *which* refusals exist and what they
name — an unusable change dropped silently would be worse than any of them.
"""

from __future__ import annotations

import pytest

from src.application.modeling.proposal_edit import ProposalEdit
from src.application.modeling.proposal_standing import PendingProposal
from src.application.modeling.submission_set import UnsubmittableSet, compose
from src.domain.submission_phase import ImpossibleSubmission

TARGET = "REQ@1712870400.eeeeeee.two-tier-repositories"
OTHER = "REQ@1712870400.fffffff.something-else"


def _proposal(proposal_id: str, *, target: str = TARGET, state: str = "draft", **fields: object):  # noqa: ANN003, ANN201
    return PendingProposal(
        proposal_id=proposal_id,
        target_id=target,
        reference_id="GAR@1780000001.bbbbbbb.two-tier-repositories",
        changed_fields=tuple(sorted(fields)),
        base_revision="abc123",
        state=state,
        edit=ProposalEdit(kind="entity", artifact_id=target, fields=dict(fields)),
    )


def _pending(*proposals: PendingProposal) -> dict[str, tuple[PendingProposal, ...]]:
    grouped: dict[str, tuple[PendingProposal, ...]] = {}
    for proposal in proposals:
        grouped[proposal.target_id] = (*grouped.get(proposal.target_id, ()), proposal)
    return grouped


def test_the_set_is_in_the_order_the_caller_gave() -> None:
    """Replay follows this order, so it is the command's rather than the repository's."""
    first = _proposal("PCH@1.aaaaaaa.one", summary="First")
    second = _proposal("PCH@2.bbbbbbb.two", name="Second")

    composed = compose(("PCH@2.bbbbbbb.two", "PCH@1.aaaaaaa.one"), _pending(first, second))

    assert [p.proposal_id for p in composed] == ["PCH@2.bbbbbbb.two", "PCH@1.aaaaaaa.one"]


def test_an_id_naming_no_live_change_is_refused() -> None:
    with pytest.raises(UnsubmittableSet, match="not a live change"):
        compose(("PCH@9.zzzzzzz.gone",), _pending(_proposal("PCH@1.aaaaaaa.one", summary="First")))


def test_a_change_already_submitted_is_refused_and_pointed_at_rebase() -> None:
    """Submitting it again would open a second branch for the same work."""
    sent = _proposal("PCH@1.aaaaaaa.one", state="submitted", summary="First")

    with pytest.raises(UnsubmittableSet, match="already been submitted"):
        compose(("PCH@1.aaaaaaa.one",), _pending(sent))


def test_the_rules_about_the_ids_themselves_come_from_their_owner() -> None:
    """Not restated here: `submission_phase` decides what a list of ids may be, and the intent it
    later builds asks the same function, so the two cannot drift."""
    with pytest.raises(ImpossibleSubmission, match="at least one"):
        compose((), {})
    with pytest.raises(ImpossibleSubmission, match="names a change twice"):
        compose(
            ("PCH@1.aaaaaaa.one", "PCH@1.aaaaaaa.one"),
            _pending(_proposal("PCH@1.aaaaaaa.one", summary="Once")),
        )


def test_two_changes_writing_one_field_of_one_artifact_are_refused() -> None:
    """Whichever replayed second would silently overwrite the other."""
    first = _proposal("PCH@1.aaaaaaa.one", summary="First wording")
    second = _proposal("PCH@2.bbbbbbb.two", summary="Second wording")

    with pytest.raises(UnsubmittableSet, match="both change the 'summary'"):
        compose(("PCH@1.aaaaaaa.one", "PCH@2.bbbbbbb.two"), _pending(first, second))


def test_the_overlap_is_found_wherever_the_two_sit_in_the_order() -> None:
    """Over the set, not over consecutive pairs — an arrangement that separates the two would
    otherwise pass the check that exists to catch it."""
    first = _proposal("PCH@1.aaaaaaa.one", summary="First wording")
    between = _proposal("PCH@2.bbbbbbb.two", target=OTHER, name="Unrelated")
    last = _proposal("PCH@3.ccccccc.three", summary="Second wording")

    with pytest.raises(UnsubmittableSet, match="both change the 'summary'"):
        compose(
            ("PCH@1.aaaaaaa.one", "PCH@2.bbbbbbb.two", "PCH@3.ccccccc.three"),
            _pending(first, between, last),
        )


def test_different_fields_of_one_artifact_compose() -> None:
    """The ordinary case the refusal must not catch: a set of changes to one artifact is the whole
    point of submitting a set."""
    first = _proposal("PCH@1.aaaaaaa.one", summary="New wording")
    second = _proposal("PCH@2.bbbbbbb.two", name="New name")

    composed = compose(("PCH@1.aaaaaaa.one", "PCH@2.bbbbbbb.two"), _pending(first, second))

    assert len(composed) == 2


def test_one_field_of_two_different_artifacts_composes() -> None:
    first = _proposal("PCH@1.aaaaaaa.one", summary="One")
    second = _proposal("PCH@2.bbbbbbb.two", target=OTHER, summary="Two")

    composed = compose(("PCH@1.aaaaaaa.one", "PCH@2.bbbbbbb.two"), _pending(first, second))

    assert len(composed) == 2
