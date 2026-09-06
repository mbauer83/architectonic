"""The local changes this repository is holding, as someone looking at a list of them needs them.

A change is stored as an internal artifact addressed to an *enterprise* id, and neither of those is
something a reader can act on: they cannot open the enterprise artifact, and they never authored the
change file. So a row names the artifact the way this repository addresses it — through the reference
that stands for it — and says what the change does to it in the vocabulary of fields, not of files.

**The condition is computed, never stored.** Whether a change has gone stale is a fact about the
enterprise artifact *now*, and `proposal_standing` owns deciding it. This module asks; it does not
grow a second opinion, which is how one word comes to mean two things.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.modeling.edit_field_catalogue import ArtifactKind
from src.application.modeling.proposal_standing import (
    PendingProposal,
    enterprise_revision,
    pending_proposals,
    standing_for,
)
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.domain.baseline_standing import ChangeCondition, Proposed

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository
    from src.domain.ontology_representation.artifact_types import EntityRecord


@dataclass(frozen=True, slots=True)
class RecordedChange:
    """One live local change against one promoted artifact."""

    change_id: str
    target_id: str
    #: What the artifact is called, and how this repository addresses it. `reference_id` is None on
    #: a deployment reading the enterprise artifact directly, where there is no proxy to link to.
    target_name: str
    reference_id: str | None
    kind: ArtifactKind
    changed_fields: tuple[str, ...]
    state: str
    condition: ChangeCondition


def recorded_changes(repo: "ArtifactRepository | None") -> tuple[RecordedChange, ...]:
    """Every live change, ordered by the artifact it changes.

    By name rather than by id, because that is the order a reader is scanning in, and by change id
    within an artifact so two changes against one artifact keep a stable order between reads.
    """
    if repo is None:
        return ()
    pending = pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))
    if not pending:
        return ()
    rows = [
        _row(proposal, repo.get_entity(proposal.reference_id), _condition_of(repo, target, pending))
        for target, proposals in pending.items()
        for proposal in proposals
    ]
    return tuple(sorted(rows, key=lambda row: (row.target_name.casefold(), row.change_id)))


def _condition_of(
    repo: "ArtifactRepository",
    target: str,
    pending: Mapping[str, tuple[PendingProposal, ...]],
) -> ChangeCondition:
    standing = standing_for(target, pending, revision_of=lambda t: enterprise_revision(repo, t))
    return standing.condition if isinstance(standing, Proposed) else "current"


def _row(
    proposal: PendingProposal,
    reference: "EntityRecord | None",
    condition: ChangeCondition,
) -> RecordedChange:
    name = reference.name if reference is not None and reference.name else proposal.target_id
    return RecordedChange(
        change_id=proposal.proposal_id,
        target_id=proposal.target_id,
        target_name=name,
        reference_id=proposal.reference_id or None,
        kind=proposal.edit.kind,
        changed_fields=proposal.changed_fields,
        state=proposal.state,
        condition=condition,
    )
