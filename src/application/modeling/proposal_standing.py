"""Which artifacts carry local changes, and which parts of them — the read side of a proposal.

A reader of an artifact must be able to see whether what is shown is the enterprise baseline or the
baseline plus changes not yet accepted upstream. `src/domain/baseline_standing.py` is the value that
says so; this module works it out from the proposals in the repository.

**Batch-shaped, and reading no index of its own.** Proposals are few — one per pending edit against one
enterprise artifact — while a list read answers over hundreds of records. So the proposals are gathered
once per call and grouped by target, rather than each record asking. That is also why there is no
reverse map in the index for this: the index maintains one for global references at three sites (each
entity, each un-index, and the full rebuild), and a second map of the same shape earns its maintenance
cost only if a measurement says the grouping is hot. None does yet.

**`conflicting` is not decided here.** The condition vocabulary has three values, and this resolver
produces two of them: `current` when the enterprise artifact is still what the change was written
against, `stale` when it has moved. Whether a change *conflicts* is the outcome of rehearsing a rebase
in a real worktree, which is a later milestone's work — and inventing a second, cheaper meaning for the
word here is how one name comes to mean two things in one system.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from src.application.modeling.proposal_edit import UnproposableEdit, from_mapping
from src.application.modeling.proposed_change import (
    BASE_REVISION,
    PENDING_STATES,
    PROPOSAL_STATE,
    PROPOSED_CHANGE_TYPE,
    PROPOSES_CHANGE_TO,
    RECORDED_EDIT,
)
from src.domain.baseline_standing import BASELINE, BaselineStanding, ChangeCondition, Proposed
from src.domain.ontology_representation.artifact_types import EntityRecord

#: What the resolver is given for one artifact's current content. `None` where the artifact cannot be
#: read — an enterprise repository that is not mounted, or a target that no longer exists. A revision
#: that cannot be taken makes staleness undecidable, which reads as `current` rather than as a guess
#: in the alarming direction: telling an author their work is stale when the evidence is missing costs
#: them a rebase they did not need.
RevisionReader = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class PendingProposal:
    """One live change, reduced to what a reader of its target needs to know."""

    proposal_id: str
    target_id: str
    changed_fields: tuple[str, ...]
    base_revision: str


def pending_proposals(entities: Iterable[EntityRecord]) -> Mapping[str, tuple[PendingProposal, ...]]:
    """Every live change, grouped by the enterprise artifact it is against.

    A record that does not decode — no target, no readable edit, a state outside the vocabulary — is
    left out rather than raised on. The verifier already refuses those (E145 to E149) and says exactly
    what is wrong with them; a read path that failed instead would take the whole page down over one
    malformed file, and hide every other artifact's standing behind it.
    """
    grouped: dict[str, list[PendingProposal]] = {}
    for record in entities:
        if record.artifact_type != PROPOSED_CHANGE_TYPE:
            continue
        proposal = _decode(record)
        if proposal is not None:
            grouped.setdefault(proposal.target_id, []).append(proposal)
    return {target: tuple(sorted(items, key=lambda p: p.proposal_id)) for target, items in grouped.items()}


def standing_for(
    target_id: str,
    pending: Mapping[str, tuple[PendingProposal, ...]],
    *,
    revision_of: RevisionReader,
) -> BaselineStanding:
    """How the artifact at `target_id` stands, given the live changes against it."""
    proposals = pending.get(target_id, ())
    if not proposals:
        return BASELINE
    return Proposed(
        proposal_ids=tuple(p.proposal_id for p in proposals),
        changed_fields=_union_of_changed_fields(proposals),
        base_revision=proposals[0].base_revision,
        condition=_condition(proposals, revision_of(target_id)),
    )


def _union_of_changed_fields(proposals: tuple[PendingProposal, ...]) -> tuple[str, ...]:
    """Every field any live change touches, in a stable order.

    The union rather than the first proposal's: two changes against one artifact are ordinary, and a
    reader asking which parts are local wants both answers, not whichever was written first.
    """
    return tuple(sorted({field for proposal in proposals for field in proposal.changed_fields}))


def _condition(proposals: tuple[PendingProposal, ...], current: str | None) -> ChangeCondition:
    if current is None:
        return "current"
    return "current" if all(p.base_revision == current for p in proposals) else "stale"


def _decode(record: EntityRecord) -> PendingProposal | None:
    target = record.extra.get(PROPOSES_CHANGE_TO)
    if not isinstance(target, str) or not target.strip():
        return None
    if str(record.extra.get(PROPOSAL_STATE, "")) not in PENDING_STATES:
        return None
    edit = record.extra.get(RECORDED_EDIT)
    if not isinstance(edit, Mapping):
        return None
    try:
        recorded = from_mapping(edit)
    except (UnproposableEdit, KeyError, TypeError, ValueError):
        return None
    base = record.extra.get(BASE_REVISION)
    if not isinstance(base, str) or not base.strip():
        return None
    return PendingProposal(
        proposal_id=record.artifact_id,
        target_id=target.strip(),
        changed_fields=tuple(sorted(recorded.fields)),
        base_revision=base.strip(),
    )
