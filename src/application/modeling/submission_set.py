"""Which changes one submission carries, in which order, or a refusal naming what is wrong.

A submission is a *set*, not a change at a time: the enterprise owner's unit of review is a coherent
group, and the branch carries all of them or none. So the set is composed and judged before anything
is replayed, because every refusal here is cheaper and clearer than the same problem discovered
halfway through writing to the enterprise repository.

**The order is the caller's, and it is part of the command.** Several changes against one artifact
are ordinary, so replay order decides the resulting content. Inferring it from filesystem order,
selection order or timestamps would make the same submission produce different content on different
machines. `submission_phase` owns what makes a list of ids submittable at all — non-empty, no
repeats — and is asked here rather than restated, so the answer cannot drift between the two places
that need it.

**Overlap is refused whatever the order.** Two changes that write the same field of the same
artifact have no defensible replay: whichever runs second wins, silently, over model content that a
reviewer will read as deliberate. Sequencing two edits of one field is a different feature; an
implicit last-writer-wins is not a governance workflow.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.application.modeling.proposal_standing import PendingProposal
from src.application.modeling.proposed_change import DRAFT_STATE
from src.domain.submission_phase import validate_proposal_ids


class UnsubmittableSet(ValueError):
    """The named changes cannot be submitted together. The message says which, and why."""


def compose(
    proposal_ids: Sequence[str],
    pending: Mapping[str, tuple[PendingProposal, ...]],
) -> tuple[PendingProposal, ...]:
    """The changes `proposal_ids` names, in that order, ready to replay.

    Raises `UnsubmittableSet` rather than returning a partial set: a submission that dropped an
    unusable change would publish a branch the author did not ask for and mark the rest submitted
    against it.
    """
    validate_proposal_ids(tuple(proposal_ids))
    by_id = {proposal.proposal_id: proposal for group in pending.values() for proposal in group}
    composed = tuple(_live(by_id, proposal_id) for proposal_id in proposal_ids)
    _refuse_overlap(composed)
    return composed


def _live(by_id: Mapping[str, PendingProposal], proposal_id: str) -> PendingProposal:
    """The change that id names, refusing one that is not a draft anyone can submit."""
    proposal = by_id.get(proposal_id)
    if proposal is None:
        raise UnsubmittableSet(
            f"'{proposal_id}' is not a live change in this repository. A change that was integrated "
            "or withdrawn is a record of what happened and is not submitted again."
        )
    if proposal.state != DRAFT_STATE:
        raise UnsubmittableSet(
            f"'{proposal_id}' has already been submitted. Rebasing it is what puts it back in front "
            "of a reviewer on the current head; submitting it again would open a second branch for "
            "the same work."
        )
    return proposal


def _refuse_overlap(composed: tuple[PendingProposal, ...]) -> None:
    """Refuse two changes writing one field of one artifact, naming both and the field.

    Stated over the *set* rather than over consecutive pairs: the two need not be adjacent in the
    order, and a rule that only looked at neighbours would pass the arrangement that hides the
    problem.
    """
    claimed: dict[tuple[str, str], str] = {}
    for proposal in composed:
        for field in proposal.edit.fields:
            owner = claimed.setdefault((proposal.edit.artifact_id, field), proposal.proposal_id)
            if owner != proposal.proposal_id:
                raise UnsubmittableSet(
                    f"'{owner}' and '{proposal.proposal_id}' both change the {field!r} of "
                    f"'{proposal.edit.artifact_id}'. Whichever replayed second would silently "
                    "overwrite the other, so the pair is refused rather than ordered."
                )
